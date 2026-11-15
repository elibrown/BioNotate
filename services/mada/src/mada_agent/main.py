"""FastAPI entry point: `uvicorn mada_agent.main:app` (run ONE worker: there is one model slot)."""

from __future__ import annotations

import asyncio
import logging
import uuid
from contextlib import asynccontextmanager
from typing import Any, Callable

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .agent_service import ClinicalAgent
from .config import Settings, get_settings
from .ingest_service import build_index
from .knowledge import load_knowledge
from .llm_client import LlamaClient, ProbeResult
from .prompt_templates import PROMPT_VERSION
from .routers.clinical import router as clinical_router

log = logging.getLogger("mada_agent")


def create_app(settings: Settings | None = None, llm: LlamaClient | None = None,
               embedding_factory: Callable[[], Any] | None = None, run_probe: bool = True) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        kb = load_knowledge(settings.rules_path, settings.checks_path)  # fail fast on bad knowledge files
        index = build_index(kb, settings.embed_model_dir, settings.chroma_dir, embedding_factory)
        client = llm or LlamaClient(settings.llama_server_url, settings.inference_timeout_s,
                                    settings.llm_max_tokens, settings.llm_temperature,
                                    enable_thinking=settings.llm_enable_thinking)
        app.state.agent = ClinicalAgent(kb, index, client, settings)
        app.state.probe = ProbeResult()
        task = None
        if run_probe:
            async def _probe() -> None:
                app.state.probe = await client.wait_until_ready(settings.probe_media, settings.startup_wait_s)
            task = asyncio.create_task(_probe())
        else:
            app.state.probe = ProbeResult(ok=True, state="ok", detail="probe disabled")
        yield
        if task:
            task.cancel()
        if llm is None:
            await client.aclose()

    app = FastAPI(title="MADA Clinical Agent", version="0.1.0", lifespan=lifespan)
    app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_credentials=False,
                       allow_methods=["GET", "POST"], allow_headers=["*"])

    @app.middleware("http")
    async def request_id(request: Request, call_next):
        rid = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
        response = await call_next(request)
        response.headers["x-request-id"] = rid
        log.info("rid=%s %s %s -> %s", rid, request.method, request.url.path, response.status_code)
        return response

    @app.get("/health")
    async def health(request: Request) -> JSONResponse:
        probe: ProbeResult = getattr(request.app.state, "probe", ProbeResult())
        agent = getattr(request.app.state, "agent", None)
        body = {
            "status": probe.state,
            "detail": probe.detail,
            "model": {"quant": settings.model_quant, "server": settings.llama_server_url, **probe.server_props},
            "modalities": {"text": probe.text_ok, "image": probe.image_ok, "audio": probe.audio_ok},
            "prompt_version": PROMPT_VERSION,
            "knowledge": {"protocols": len(agent.kb.protocols), "checks": len(agent.kb.checks)} if agent else None,
        }
        return JSONResponse(body, status_code=200 if probe.ok else 503)

    app.include_router(clinical_router)
    return app


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
app = create_app()
