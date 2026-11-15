"""Service settings, read from environment variables (or a `.env` file)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

MODULE_ROOT = Path(__file__).resolve().parents[2]
PACKAGE_DATA = Path(__file__).resolve().parent / "data"


def _knowledge_file(name: str) -> Path:
    """Repo-root copy when running from source; the copy bundled in the wheel otherwise."""
    root = MODULE_ROOT / name
    return root if root.exists() else PACKAGE_DATA / name


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Model server (llama.cpp `llama-server`, OpenAI-compatible API)
    llama_server_url: str = Field("http://localhost:8080", alias="LLAMA_SERVER_URL")
    model_quant: str = Field("gemma-4-E2B-it QAT Q4_0 GGUF", alias="MODEL_QUANT")
    llm_max_tokens: int = Field(600, alias="LLM_MAX_TOKENS")
    llm_temperature: float = Field(0.1, alias="LLM_TEMPERATURE")
    llm_enable_thinking: bool = Field(False, alias="LLM_ENABLE_THINKING")

    # Knowledge files
    rules_path: Path = Field(default_factory=lambda: _knowledge_file("rules.md"), alias="RULES_PATH")
    checks_path: Path = Field(default_factory=lambda: _knowledge_file("checks.md"), alias="CHECKS_PATH")

    # Retrieval
    chroma_dir: Path | None = Field(None, alias="CHROMA_DIR")  # None = in-memory index rebuilt at startup
    embed_model_dir: Path = Field(MODULE_ROOT / "models" / "embeddings", alias="EMBED_MODEL_DIR")
    retrieval_top_k: int = Field(5, alias="RETRIEVAL_TOP_K")
    # Always offer the model every life-threatening protocol, so weak retrieval can never hide one.
    always_include_life_threatening: bool = Field(True, alias="ALWAYS_INCLUDE_LIFE_THREATENING")

    # Conversation
    max_rounds: int = Field(3, alias="MAX_ROUNDS")
    max_checks_per_round: int = Field(3, alias="MAX_CHECKS_PER_ROUND")

    # Media
    max_upload_mb: float = Field(10.0, alias="MAX_UPLOAD_MB")
    max_image_px: int = Field(896, alias="MAX_IMAGE_PX")
    max_audio_s: float = Field(30.0, alias="MAX_AUDIO_S")

    # Concurrency / timeouts (seconds)
    queue_timeout_s: float = Field(30.0, alias="QUEUE_TIMEOUT_S")
    inference_timeout_s: float = Field(60.0, alias="INFERENCE_TIMEOUT_S")
    startup_wait_s: float = Field(300.0, alias="STARTUP_WAIT_S")
    probe_media: bool = Field(True, alias="PROBE_MEDIA")

    # HTTP
    cors_origins_raw: str = Field("http://localhost:3000", alias="CORS_ORIGINS")

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.cors_origins_raw.split(",") if o.strip()]

    @property
    def max_upload_bytes(self) -> int:
        return int(self.max_upload_mb * 1024 * 1024)


@lru_cache
def get_settings() -> Settings:
    return Settings()
