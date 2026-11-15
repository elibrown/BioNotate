from __future__ import annotations

import hashlib
import re
from pathlib import Path

import numpy as np
import pytest

from mada_agent.config import Settings
from mada_agent.knowledge import load_knowledge

ROOT = Path(__file__).resolve().parents[1]


class HashEmbedding:
    """Deterministic bag-of-words embedding so tests need no model download."""

    def __init__(self, dim: int = 256):
        self.dim = dim

    def __call__(self, input):  # noqa: A002 - chroma signature
        out = []
        for text in input:
            v = np.zeros(self.dim, dtype=np.float32)
            for tok in re.findall(r"[a-z0-9]+", text.lower()):
                v[int(hashlib.md5(tok.encode()).hexdigest(), 16) % self.dim] += 1.0
            n = np.linalg.norm(v)
            out.append((v / n if n else v).tolist())
        return out

    # chroma >= 0.5 embedding-function protocol helpers
    def name(self) -> str:
        return "test-hash"

    def embed_query(self, input):  # noqa: A002
        return self(input)

    def embed_documents(self, input):  # noqa: A002
        return self(input)

    def is_legacy(self) -> bool:
        return True

    def get_config(self):
        return {}

    def default_space(self):
        return "cosine"

    def supported_spaces(self):
        return ["cosine", "l2", "ip"]


@pytest.fixture(scope="session")
def kb():
    return load_knowledge(ROOT / "rules.md", ROOT / "checks.md")


@pytest.fixture
def settings():
    return Settings(LLAMA_SERVER_URL="http://llama.test", QUEUE_TIMEOUT_S=1, INFERENCE_TIMEOUT_S=2)
