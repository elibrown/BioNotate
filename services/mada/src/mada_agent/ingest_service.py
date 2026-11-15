"""Vector index of the Protocols (ChromaDB) used to shortlist candidates for the model.

Two chunks per Protocol (official title + display steps; lay retrieval description), metadata
{protocol_id, severity}; a Protocol ranks by its best chunk. The embedding model
(all-MiniLM-L6-v2, ONNX) is loaded from `EMBED_MODEL_DIR`, which `scripts/prepare_models.py`
fills, so the service needs no network at runtime.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable

from .knowledge import KnowledgeBase

log = logging.getLogger(__name__)
COLLECTION = "iss_emergency_protocols"


class IndexError_(RuntimeError):
    pass


def onnx_embedding_function(model_dir: Path, allow_download: bool = False) -> Any:
    """Chroma's bundled all-MiniLM-L6-v2 ONNX embedder, pointed at a project-local folder."""
    from chromadb.utils.embedding_functions.onnx_mini_lm_l6_v2 import ONNXMiniLM_L6_V2

    ef = ONNXMiniLM_L6_V2()
    ef.DOWNLOAD_PATH = model_dir  # type: ignore[misc]
    if not allow_download and not (model_dir / ef.EXTRACTED_FOLDER_NAME / "model.onnx").exists():
        raise IndexError_(f"embedding model not found in {model_dir}; run scripts/prepare_models.py")
    return ef


def protocol_chunks(kb: KnowledgeBase, pid: str) -> list[tuple[str, str]]:
    """(chunk_id, text) pairs for one Protocol: the official text, and the lay description if any."""
    p = kb.protocols[pid]
    chunks = [(f"{pid}#protocol", "\n".join([p.title, *p.display_steps]))]
    if p.retrieval_description:
        chunks.append((f"{pid}#lay", p.retrieval_description))
    return chunks


class ProtocolIndex:
    def __init__(self, kb: KnowledgeBase, embedding_function: Any, persist_dir: Path | None = None):
        import chromadb
        from chromadb.config import Settings as ChromaSettings

        settings = ChromaSettings(anonymized_telemetry=False)
        if persist_dir is not None:
            client = chromadb.PersistentClient(path=str(persist_dir), settings=settings)
        else:
            client = chromadb.EphemeralClient(settings=settings)
        # Rebuilt at every startup from rules.md, so the index can never drift from the source.
        try:
            client.delete_collection(COLLECTION)
        except Exception:
            pass
        self._col = client.create_collection(COLLECTION, embedding_function=embedding_function,
                                             metadata={"hnsw:space": "cosine"})
        chunks = [(cid, text, pid) for pid in kb.protocols for cid, text in protocol_chunks(kb, pid)]
        self._col.add(ids=[c[0] for c in chunks], documents=[c[1] for c in chunks],
                      metadatas=[{"protocol_id": c[2], "severity": kb.protocols[c[2]].severity} for c in chunks])
        self.size = len(kb.protocols)
        self._n_chunks = len(chunks)
        log.info("indexed %d protocols (%d chunks)", self.size, self._n_chunks)

    def shortlist(self, query: str, k: int, where: dict[str, Any] | None = None) -> list[str]:
        """Top-k protocol IDs, ranked by their best-matching chunk."""
        if not query.strip():
            return []
        res = self._col.query(query_texts=[query], n_results=self._n_chunks, where=where)
        ranked = dict.fromkeys(m["protocol_id"] for m in res["metadatas"][0])
        return list(ranked)[:k]


def build_index(kb: KnowledgeBase, model_dir: Path, persist_dir: Path | None,
                embedding_factory: Callable[[], Any] | None = None) -> ProtocolIndex:
    ef = embedding_factory() if embedding_factory else onnx_embedding_function(model_dir)
    return ProtocolIndex(kb, ef, persist_dir)
