"""The Assessment loop: rules first, then retrieval + model, then deterministic validation.

Flow for one request:
1. Validate Check answers; compute GCS reporting and the GCS alert.
2. Deterministic fast-path rules on the answers (e.g. no response + not breathing -> CPR).
3. Retrieve a shortlist of protocols; ask the model to choose (JSON schema enforced).
4. Enforce the rules the model must not break (closed ID lists, chest-pain Checks, GCS, round limit).
5. Assemble the response: Universal first steps + verbatim Steps.
If the model is unavailable, times out or returns garbage, a degraded response is returned instead.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any

from . import checks as chk
from .config import Settings
from .gcs import check_trend
from .ingest_service import ProtocolIndex
from .knowledge import KnowledgeBase
from .llm_client import LlamaClient, LlmError, LlmTimeout, audio_part, image_part, text_part
from .prompt_templates import (PROMPT_VERSION, decision_schema, few_shot_messages, render_assessment, render_patient_context,
                               system_prompt)
from .schemas import AnalyzeResponse, CheckOut, Conversation, GcsOut, ProtocolOut

log = logging.getLogger(__name__)

DISCLAIMER = ("Decision support only, for use while the Crew Medical Officer is on the way. Steps are copied "
              "from the ISS Medical Checklist (JSC-48522); Checks marked UNVALIDATED are placeholders. "
              "The Crew Medical Officer's judgement overrides this tool.")
NO_MATCH_MESSAGE = "No protocol matches. Keep the Patient safe; the Crew Medical Officer must assess."


class QueueTimeout(RuntimeError):
    """Waited too long for the single model slot."""


@dataclass
class MediaInput:
    image_data_uri: str | None = None
    audio_wav_b64: str | None = None


class ClinicalAgent:
    def __init__(self, kb: KnowledgeBase, index: ProtocolIndex, llm: LlamaClient, settings: Settings):
        self.kb = kb
        self.index = index
        self.llm = llm
        self.settings = settings
        self._lock = asyncio.Lock()

    # ---------- helpers ----------
    def _protocol_out(self, pid: str) -> ProtocolOut:
        p = self.kb.protocols[pid]
        return ProtocolOut(id=p.id, title=p.title, severity=p.severity, steps=p.display_steps)  # type: ignore[arg-type]

    def _check_out(self, cid: str) -> CheckOut:
        c = self.kb.checks[cid]
        return CheckOut(id=c.id, title=c.title, instruction=c.instruction, status=c.status,  # type: ignore[arg-type]
                        answer=c.answer)

    def _query_text(self, conv: Conversation, answers: dict[str, Any]) -> str:
        texts = [t.text for t in conv.turns if t.role == "responder" and t.text]
        texts += [f"{k} {v}" for k, v in answers.items() if k != "GCS"]
        return "\n".join(texts)

    def shortlist(self, conv: Conversation, answers: dict[str, Any], extra: list[str]) -> list[str]:
        ids = self.index.shortlist(self._query_text(conv, answers), self.settings.retrieval_top_k)
        if self.settings.always_include_life_threatening:
            ids += sorted(self.kb.life_threatening_ids)
        ids += extra
        return list(dict.fromkeys(i for i in ids if i in self.kb.protocols))

    # ---------- main entry ----------
    async def assess(self, conv: Conversation, media: MediaInput) -> AnalyzeResponse:
        t0 = time.perf_counter()
        state = chk.collect_answers(self.kb, conv.turns)
        answers = state.latest
        round_no = sum(1 for t in conv.turns if t.role == "agent" and t.asked_check_ids)
        gcs = GcsOut(
            latest=state.gcs_readings[-1].components if state.gcs_readings else None,
            total=state.gcs_readings[-1].total if state.gcs_readings else None,
            history=[r.as_dict() for r in sorted(state.gcs_readings, key=lambda r: r.timestamp)],
        )
        alert = check_trend(state.gcs_readings)
        base = dict(gcs=gcs, gcs_alert=alert.as_dict() if alert else None, answer_warnings=state.warnings,
                    round=round_no)

        fp = chk.fast_path(self.kb, answers)
        if fp:
            pid, _rule = fp
            return self._finalize([pid], base, decided_by="fast_path_rule", degraded=False,
                                  rationale=f"Fast-path rule on Check answers -> {pid}.", t0=t0)

        previously_given = [p for t in conv.turns if t.role == "agent" for p in t.protocol_ids]
        shortlist = self.shortlist(conv, answers, previously_given)
        try:
            decision = await self._ask_model(conv, state, round_no, shortlist, media)
        except QueueTimeout:
            raise
        except LlmError as exc:
            log.warning("model unavailable, degraded response: %s", exc)
            return self._degraded(conv, answers, base, t0)

        # The app has the authoritative Patient/Responder identity. Do not let
        # an LLM guess override the selected patient when identities are known.
        if conv.patient_context and conv.patient_context.responder_is_patient is not None:
            decision["patient_is_responder"] = conv.patient_context.responder_is_patient
        return self._apply_decision(decision, shortlist, answers, state, round_no, base, t0, conv.turns)

    async def _ask_model(self, conv: Conversation, state: chk.AnswerState, round_no: int, shortlist: list[str],
                         media: MediaInput) -> dict[str, Any]:
        notes = []
        if round_no >= self.settings.max_rounds:
            notes.append("ROUND LIMIT REACHED: you must finalize now.")
        if chk.needs_gcs(state.latest):
            notes.append("The Patient is not clearly alert: GCS is needed.")
        user_text = render_assessment(conv.turns, round_no, self.settings.max_rounds, state.latest, state.warnings,
                                      media.image_data_uri is not None, media.audio_wav_b64 is not None, notes)
        # Clinical rules and fast paths only use the Responder's report/Checks.
        # Historical readings are *additional context* for the model, not facts
        # that automatically trigger an emergency protocol.
        user_text += render_patient_context(conv.patient_context)
        content: list[dict[str, Any]] = []
        if media.image_data_uri:
            content.append(image_part(media.image_data_uri))
        if media.audio_wav_b64:
            content.append(audio_part(media.audio_wav_b64))
        content.append(text_part(user_text))
        messages = [{"role": "system", "content": system_prompt(self.kb, shortlist)},
                    *few_shot_messages(shortlist),
                    {"role": "user", "content": content}]
        schema = decision_schema(shortlist, list(self.kb.checks), self.settings.max_checks_per_round)

        try:
            await asyncio.wait_for(self._lock.acquire(), timeout=self.settings.queue_timeout_s)
        except asyncio.TimeoutError as exc:
            raise QueueTimeout("model is busy; try again") from exc
        try:
            return await asyncio.wait_for(self.llm.chat_json(messages, schema),
                                          timeout=self.settings.inference_timeout_s)
        except asyncio.TimeoutError as exc:
            raise LlmTimeout("model inference timed out") from exc
        finally:
            self._lock.release()

    def _apply_decision(self, d: dict[str, Any], shortlist: list[str], answers: dict[str, Any],
                        state: chk.AnswerState, round_no: int, base: dict[str, Any], t0: float,
                        turns: list[Any]) -> AnalyzeResponse:
        protocol_ids = [p for p in d.get("protocol_ids", []) if p in shortlist][:3]
        protocol_ids = list(dict.fromkeys(protocol_ids))
        check_ids = [c for c in d.get("check_ids", []) if c in self.kb.checks]
        # never re-ask an answered Check (GCS may be repeated to follow a trend)
        check_ids = [c for c in dict.fromkeys(check_ids) if c == "GCS" or c not in answers]
        # never re-ask a Check the Responder was already asked (they answered it or could not do it)
        already_asked = {c for t in turns if t.role == "agent" for c in t.asked_check_ids}
        check_ids = [c for c in check_ids if c == "GCS" or c not in already_asked]
        # re-ask Checks whose answers were invalid
        for w in state.warnings:
            if w["check_id"] in self.kb.checks and w["check_id"] not in check_ids:
                check_ids.append(w["check_id"])
        action = d.get("action")
        extra = dict(observed_features=[str(f)[:80] for f in d.get("observed_features", [])][:6],
                     rationale=str(d.get("rationale", ""))[:500] or None)

        limit_reached = round_no >= self.settings.max_rounds
        has_life_threat = any(self.kb.protocols[p].severity == "life_threatening" for p in protocol_ids)

        if action == "finalize" and not has_life_threat and not limit_reached:
            pending: list[str] = []
            if chk.chest_pain_present(answers, bool(d.get("chest_pain_reported"))):
                pending += chk.missing_chest_pain_checks(self.kb, answers)
            if chk.needs_gcs(answers) and not d.get("patient_is_responder"):
                pending.append("GCS")
            pending = [c for c in pending if c not in already_asked]  # asked before and not doable
            if pending:
                action, check_ids = "ask_checks", list(dict.fromkeys(pending + check_ids))
        if action == "ask_checks":
            if (chk.needs_gcs(answers) and "GCS" not in check_ids and "GCS" not in already_asked
                    and not d.get("patient_is_responder")):
                check_ids.insert(0, "GCS")
            if limit_reached or not check_ids:
                action = "finalize"
        if action == "finalize":
            return self._finalize(protocol_ids, base, decided_by="model", degraded=False, t0=t0, **extra)

        check_ids = check_ids[: self.settings.max_checks_per_round]
        resp = AnalyzeResponse(
            prompt_version=PROMPT_VERSION, model_quant=self.settings.model_quant, degraded=False,
            action="ask_checks", first_steps=list(self.kb.universal_first_steps),
            severity=self.kb.max_severity(protocol_ids),  # type: ignore[arg-type]
            protocols=[], next_checks=[self._check_out(c) for c in check_ids], decided_by="model",
            disclaimer=DISCLAIMER, **base, **extra)
        self._log(resp, t0)
        return resp

    def _finalize(self, protocol_ids: list[str], base: dict[str, Any], decided_by: str, degraded: bool,
                  t0: float, rationale: str | None = None, observed_features: list[str] | None = None,
                  ) -> AnalyzeResponse:
        resp = AnalyzeResponse(
            prompt_version=PROMPT_VERSION, model_quant=self.settings.model_quant, degraded=degraded,
            action="finalize", first_steps=list(self.kb.universal_first_steps),
            severity=self.kb.max_severity(protocol_ids),  # type: ignore[arg-type]
            protocols=[self._protocol_out(p) for p in protocol_ids],
            no_protocol_match=not protocol_ids, message=None if protocol_ids else NO_MATCH_MESSAGE,
            next_checks=[], observed_features=observed_features or [], rationale=rationale,
            decided_by=decided_by, disclaimer=DISCLAIMER, **base)  # type: ignore[arg-type]
        self._log(resp, t0)
        return resp

    def _degraded(self, conv: Conversation, answers: dict[str, Any], base: dict[str, Any], t0: float) -> AnalyzeResponse:
        ids = self.index.shortlist(self._query_text(conv, answers), min(3, self.settings.retrieval_top_k))
        resp = AnalyzeResponse(
            prompt_version=PROMPT_VERSION, model_quant=self.settings.model_quant, degraded=True,
            action="finalize", first_steps=list(self.kb.universal_first_steps),
            severity=self.kb.max_severity(ids),  # type: ignore[arg-type]
            protocols=[self._protocol_out(p) for p in ids], no_protocol_match=not ids,
            message=("The AI model is unavailable. These protocols were matched by text search only and may be "
                     "wrong; the Crew Medical Officer must decide."),
            next_checks=[], decided_by="retrieval_only", disclaimer=DISCLAIMER, **base)
        self._log(resp, t0)
        return resp

    @staticmethod
    def _log(resp: AnalyzeResponse, t0: float) -> None:
        # Never log symptom text, media or rationale (docs/adr/0005).
        log.info("assessment action=%s protocols=%s severity=%s decided_by=%s degraded=%s ms=%d",
                 resp.action, [p.id for p in resp.protocols], resp.severity, resp.decided_by, resp.degraded,
                 int((time.perf_counter() - t0) * 1000))
