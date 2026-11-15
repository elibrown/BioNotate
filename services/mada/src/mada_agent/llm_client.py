"""Client for llama.cpp `llama-server` (OpenAI-compatible /v1/chat/completions)."""

from __future__ import annotations

import asyncio
import base64
import io
import json
import logging
import math
import struct
import time
import wave
from dataclasses import dataclass, field
from typing import Any

import httpx

log = logging.getLogger(__name__)


class LlmError(RuntimeError):
    """The model server failed or returned something unusable."""


class LlmTimeout(LlmError):
    pass


def text_part(text: str) -> dict[str, Any]:
    return {"type": "text", "text": text}


def image_part(data_uri: str) -> dict[str, Any]:
    return {"type": "image_url", "image_url": {"url": data_uri}}


def audio_part(wav_b64: str) -> dict[str, Any]:
    return {"type": "input_audio", "input_audio": {"data": wav_b64, "format": "wav"}}


@dataclass
class ProbeResult:
    ok: bool = False
    state: str = "starting"  # starting | ok | unavailable
    detail: str = "probe not run yet"
    text_ok: bool = False
    image_ok: bool | None = None
    audio_ok: bool | None = None
    server_props: dict[str, Any] = field(default_factory=dict)
    checked_at: float | None = None


def _probe_png() -> str:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (64, 64), (200, 30, 30)).save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def _probe_wav() -> str:
    rate, n = 16_000, 16_000
    frames = b"".join(struct.pack("<h", int(8000 * math.sin(2 * math.pi * 440 * i / rate))) for i in range(n))
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(frames)
    return base64.b64encode(buf.getvalue()).decode()


_PROBE_SCHEMA = {"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]}


class LlamaClient:
    def __init__(self, base_url: str, timeout_s: float, max_tokens: int = 600, temperature: float = 0.1,
                 transport: httpx.AsyncBaseTransport | None = None, enable_thinking: bool = False):
        self.base_url = base_url.rstrip("/")
        self.timeout_s = timeout_s
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.enable_thinking = enable_thinking
        self._client = httpx.AsyncClient(base_url=self.base_url, timeout=httpx.Timeout(timeout_s, connect=5.0),
                                         transport=transport)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def chat_json(self, messages: list[dict[str, Any]], schema: dict[str, Any],
                        max_tokens: int | None = None) -> dict[str, Any]:
        body = {
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": max_tokens or self.max_tokens,
            # Gemma 4 thinks by default; the schema's `rationale` field is the reasoning step instead.
            "chat_template_kwargs": {"enable_thinking": self.enable_thinking},
            "response_format": {"type": "json_schema",
                                "json_schema": {"name": "decision", "strict": True, "schema": schema}},
        }
        try:
            r = await self._client.post("/v1/chat/completions", json=body)
        except httpx.TimeoutException as exc:
            raise LlmTimeout("model server timed out") from exc
        except httpx.HTTPError as exc:
            raise LlmError(f"model server unreachable: {exc.__class__.__name__}") from exc
        if r.status_code != 200:
            raise LlmError(f"model server returned HTTP {r.status_code}: {r.text[:300]}")
        try:
            content = r.json()["choices"][0]["message"]["content"]
            out = json.loads(content)
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise LlmError("model returned output that is not the expected JSON") from exc
        if not isinstance(out, dict):
            raise LlmError("model JSON is not an object")
        return out

    async def server_props(self) -> dict[str, Any]:
        try:
            r = await self._client.get("/props", timeout=5.0)
            if r.status_code == 200:
                p = r.json()
                gen = p.get("default_generation_settings", {})
                return {"model_path": p.get("model_path"), "n_ctx": gen.get("n_ctx"),
                        "modalities": p.get("modalities"), "build_info": p.get("build_info")}
        except (httpx.HTTPError, ValueError):
            pass
        return {}

    async def probe(self, with_media: bool) -> ProbeResult:
        """Round-trip a tiny text (+ image + audio) request to prove the model is loaded and multimodal."""
        res = ProbeResult(checked_at=time.time())
        try:
            r = await self._client.get("/health", timeout=5.0)
        except httpx.HTTPError:
            res.detail = f"model server not reachable at {self.base_url}"
            return res
        if r.status_code == 503:
            res.detail = "model server is loading the model"
            return res
        if r.status_code != 200:
            res.state, res.detail = "unavailable", f"model server health returned HTTP {r.status_code}"
            return res
        res.server_props = await self.server_props()
        ask = [text_part('Reply with the JSON {"ok": true}.')]
        try:
            await self.chat_json([{"role": "user", "content": ask}], _PROBE_SCHEMA, max_tokens=16)
            res.text_ok = True
            if with_media:
                await self.chat_json([{"role": "user", "content": [image_part(_probe_png())] + ask}],
                                     _PROBE_SCHEMA, max_tokens=16)
                res.image_ok = True
                await self.chat_json([{"role": "user", "content": [audio_part(_probe_wav())] + ask}],
                                     _PROBE_SCHEMA, max_tokens=16)
                res.audio_ok = True
        except LlmError as exc:
            missing = "image" if res.text_ok and res.image_ok is None else "audio" if res.image_ok else "text"
            res.state = "unavailable"
            res.detail = (f"no suitable hardware / model not loaded: {missing} request failed ({exc}). "
                          "Check that llama-server has the GPU, the GGUF and the mmproj file.")
            return res
        res.ok, res.state, res.detail = True, "ok", "model loaded; text" + (", image and audio" if with_media else "") + " ok"
        return res

    async def wait_until_ready(self, with_media: bool, max_wait_s: float, interval_s: float = 5.0) -> ProbeResult:
        deadline = time.monotonic() + max_wait_s
        while True:
            res = await self.probe(with_media)
            if res.ok or res.state == "unavailable" or time.monotonic() >= deadline:
                if not res.ok and res.state == "starting":
                    res.state = "unavailable"
                    res.detail = f"no suitable hardware / model not loaded after {max_wait_s:.0f} s: {res.detail}"
                log.info("model probe: %s (%s)", res.state, res.detail)
                return res
            await asyncio.sleep(interval_s)
