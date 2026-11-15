"""Download everything the service needs at runtime into ./models (gitignored).

    python scripts/prepare_models.py            # GGUF + mmproj + embedding model
    python scripts/prepare_models.py --skip-llm # embedding model only (e.g. for CI)

Files:
  models/gemma-4-E2B_q4_0-it.gguf      Google's official QAT Q4_0 weights (~3.35 GB)
  models/gemma-4-E2B-it-mmproj.gguf    vision + audio encoder (~1 GB)
  models/embeddings/onnx/...           all-MiniLM-L6-v2 (ONNX) for protocol retrieval
Re-running skips files that are already complete.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
REPO = "google/gemma-4-E2B-it-qat-q4_0-gguf"
LLM_FILES = ["gemma-4-E2B_q4_0-it.gguf", "gemma-4-E2B-it-mmproj.gguf"]


def download(url: str, dest: Path, token: str | None) -> None:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    with httpx.stream("GET", url, headers=headers, follow_redirects=True, timeout=None) as r:
        r.raise_for_status()
        total = int(r.headers.get("content-length", 0))
        if dest.exists() and total and dest.stat().st_size == total:
            print(f"  {dest.name}: already complete")
            return
        tmp = dest.with_suffix(dest.suffix + ".part")
        done = 0
        with open(tmp, "wb") as f:
            for chunk in r.iter_bytes(1 << 20):
                f.write(chunk)
                done += len(chunk)
                if total:
                    print(f"\r  {dest.name}: {done / total:6.1%} of {total / 1e9:.2f} GB", end="", flush=True)
        print()
        tmp.replace(dest)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--models-dir", type=Path, default=ROOT / "models")
    ap.add_argument("--skip-llm", action="store_true")
    args = ap.parse_args()
    args.models_dir.mkdir(parents=True, exist_ok=True)
    token = os.environ.get("HF_TOKEN")

    if not args.skip_llm:
        print(f"Downloading {REPO}")
        for name in LLM_FILES:
            download(f"https://huggingface.co/{REPO}/resolve/main/{name}", args.models_dir / name, token)

    print("Preparing embedding model (all-MiniLM-L6-v2 ONNX)")
    sys.path.insert(0, str(ROOT / "src"))
    from mada_agent.ingest_service import onnx_embedding_function

    ef = onnx_embedding_function(args.models_dir / "embeddings", allow_download=True)
    ef(["warm-up"])  # triggers the download and verifies the model runs
    print("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
