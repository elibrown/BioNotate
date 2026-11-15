"""Load and validate the clinical knowledge files (`rules.md`, `checks.md`).

Both files are Python-literal dictionaries inside markdown files. They are parsed with `ast` and
`ast.literal_eval`, never executed.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

SEVERITY_ORDER = {"urgent": 1, "life_threatening": 2}
CHECK_ANSWER_TYPES = {"gcs", "choice", "multi_choice", "number", "audio"}
GCS_COMPONENTS = ("eye", "verbal", "motor")

# "(#6)", "(#1, #3)" -> refer to the deleted biomarker guide; removed for display only.
_BM_REF = re.compile(r"\s*\(#\d+(?:\s*,\s*#\d+)*\)")


class KnowledgeError(ValueError):
    """The knowledge files are missing, malformed or inconsistent."""


def display_step(step: str) -> str:
    """Return a Step as shown to the Responder: verbatim except `(#N)` markers are removed."""
    return _BM_REF.sub("", step)


@dataclass(frozen=True)
class Protocol:
    id: str
    title: str
    steps: tuple[str, ...]  # verbatim from rules.md
    severity: str
    retrieval_description: str = ""  # search only; never shown

    @property
    def display_steps(self) -> list[str]:
        return [display_step(s) for s in self.steps]


@dataclass(frozen=True)
class Check:
    id: str
    title: str
    status: str
    source: str
    instruction: str
    answer: dict[str, Any]
    when: str | None = None

    @property
    def answer_type(self) -> str:
        return self.answer["type"]

    def gcs_levels(self, component: str) -> list[dict[str, Any]]:
        return self.answer["components"][component]


@dataclass(frozen=True)
class KnowledgeBase:
    protocols: dict[str, Protocol]
    universal_first_steps: tuple[str, ...]
    checks: dict[str, Check]
    fast_path_rules: tuple[dict[str, Any], ...]
    chest_pain_required_checks: tuple[str, ...]
    gcs_alert_rules: tuple[dict[str, Any], ...] = field(default_factory=tuple)

    def max_severity(self, protocol_ids: list[str]) -> str | None:
        sevs = [self.protocols[p].severity for p in protocol_ids if p in self.protocols]
        return max(sevs, key=SEVERITY_ORDER.__getitem__) if sevs else None

    @property
    def life_threatening_ids(self) -> set[str]:
        return {p.id for p in self.protocols.values() if p.severity == "life_threatening"}


def _literal_assignments(path: Path) -> dict[str, Any]:
    try:
        source = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise KnowledgeError(f"knowledge file not found: {path}") from exc
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError as exc:
        raise KnowledgeError(f"{path.name}: not parseable as Python literals: {exc}") from exc
    out: dict[str, Any] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            try:
                out[node.targets[0].id] = ast.literal_eval(node.value)
            except ValueError as exc:
                raise KnowledgeError(f"{path.name}: {node.targets[0].id} is not a literal") from exc
    return out


def _require(cond: bool, msg: str) -> None:
    if not cond:
        raise KnowledgeError(msg)


def load_knowledge(rules_path: Path, checks_path: Path) -> KnowledgeBase:
    rules = _literal_assignments(rules_path)
    checks_src = _literal_assignments(checks_path)

    for name in ("ISS_EMERGENCY_PROTOCOLS", "UNIVERSAL_FIRST_STEPS", "PROTOCOL_SEVERITY"):
        _require(name in rules, f"rules.md: missing {name}")
    raw_protocols: dict[str, Any] = rules["ISS_EMERGENCY_PROTOCOLS"]
    severity: dict[str, str] = rules["PROTOCOL_SEVERITY"]

    _require(set(raw_protocols) == set(severity),
             f"rules.md: PROTOCOL_SEVERITY keys {sorted(set(severity) ^ set(raw_protocols))} do not match protocols")
    protocols: dict[str, Protocol] = {}
    for pid, p in raw_protocols.items():
        _require(isinstance(p.get("title"), str) and p["title"], f"rules.md: {pid} has no title")
        steps = p.get("steps")
        _require(isinstance(steps, list) and steps and all(isinstance(s, str) for s in steps),
                 f"rules.md: {pid} has no steps")
        _require(severity[pid] in SEVERITY_ORDER, f"rules.md: {pid} has unknown severity {severity[pid]!r}")
        protocols[pid] = Protocol(pid, p["title"], tuple(steps), severity[pid],
                                  rules.get("RETRIEVAL_DESCRIPTIONS", {}).get(pid, ""))

    unknown = set(rules.get("RETRIEVAL_DESCRIPTIONS", {})) - set(raw_protocols)
    _require(not unknown, f"rules.md: RETRIEVAL_DESCRIPTIONS has unknown protocols {sorted(unknown)}")

    first_steps = rules["UNIVERSAL_FIRST_STEPS"]
    _require(isinstance(first_steps, list) and len(first_steps) >= 2, "rules.md: UNIVERSAL_FIRST_STEPS needs 2 steps")
    _require(all("Crew Medical Officer" in s for s in first_steps[1:2]),
             "rules.md: the second universal step must call the Crew Medical Officer")

    _require("CHECK_CATALOGUE" in checks_src, "checks.md: missing CHECK_CATALOGUE")
    checks: dict[str, Check] = {}
    for cid, c in checks_src["CHECK_CATALOGUE"].items():
        for key in ("title", "status", "source", "instruction", "answer"):
            _require(key in c, f"checks.md: {cid} missing {key}")
        _require(c["status"] in {"SOURCED", "UNVALIDATED"}, f"checks.md: {cid} bad status")
        atype = c["answer"].get("type")
        _require(atype in CHECK_ANSWER_TYPES, f"checks.md: {cid} unknown answer type {atype!r}")
        if atype in {"choice", "multi_choice"}:
            _require(bool(c["answer"].get("options")), f"checks.md: {cid} has no options")
        if atype == "number":
            lo, hi = c["answer"].get("plausible", (None, None))
            _require(lo is not None and hi is not None and lo < hi, f"checks.md: {cid} bad plausible range")
        if atype == "gcs":
            comps = c["answer"].get("components", {})
            _require(set(comps) == set(GCS_COMPONENTS), f"checks.md: {cid} needs eye/verbal/motor")
        checks[cid] = Check(cid, c["title"], c["status"], c["source"], c["instruction"], c["answer"], c.get("when"))
    _require("GCS" in checks, "checks.md: GCS check is required")

    fast_rules = tuple(checks_src.get("FAST_PATH_RULES", []))
    for r in fast_rules:
        _require(r.get("protocol") in protocols, f"checks.md: fast-path rule targets unknown protocol {r.get('protocol')}")
        for section in ("when", "unless"):
            for cid, values in r.get(section, {}).items():
                _require(cid in checks, f"checks.md: fast-path rule uses unknown check {cid}")
                opts = set(checks[cid].answer.get("options", []))
                _require(set(values) <= opts, f"checks.md: fast-path rule uses unknown option of {cid}")

    chest = tuple(checks_src.get("CHEST_PAIN_REQUIRED_CHECKS", []))
    _require(all(c in checks for c in chest), "checks.md: CHEST_PAIN_REQUIRED_CHECKS has unknown check")

    return KnowledgeBase(
        protocols=protocols,
        universal_first_steps=tuple(first_steps),
        checks=checks,
        fast_path_rules=fast_rules,
        chest_pain_required_checks=chest,
        gcs_alert_rules=tuple(checks_src.get("GCS_ALERT_RULES", [])),
    )
