"""Build the hand-off artefacts into ./dist:

  dist/mada_agent-<version>-py3-none-any.whl   installable package (bundles rules.md + checks.md)
  dist/mada-agent-handoff.zip                  source, docs, eval, Docker files (no models, no caches)

    python scripts/build_dist.py
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
INCLUDE = ["README.md", "GLOSSARY.md", "rules.md", "checks.md", "pyproject.toml", "Dockerfile",
           "docker-compose.yml", ".env.example", ".gitignore", "docs", "src", "tests", "eval/scenarios",
           "eval/cases", "eval/ddxplus_build.py", "eval/run_eval.py", "eval/results_*.md", "scripts"]
SKIP_PARTS = {"__pycache__", ".pytest_cache", "data", ".egg-info"}


def main() -> int:
    data = ROOT / "src" / "mada_agent" / "data"
    data.mkdir(exist_ok=True)
    for name in ("rules.md", "checks.md"):  # the repo-root files are the single source of truth
        shutil.copy2(ROOT / name, data / name)
    DIST.mkdir(exist_ok=True)
    for old in DIST.glob("mada_agent-*.whl"):
        old.unlink()
    subprocess.run([sys.executable, "-m", "pip", "wheel", "--no-deps", "--no-build-isolation", "-w", str(DIST),
                    str(ROOT)], check=True)
    shutil.rmtree(ROOT / "build", ignore_errors=True)
    wheel = next(DIST.glob("mada_agent-*.whl"))

    out = DIST / "mada-agent-handoff.zip"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for pattern in INCLUDE:
            for path in sorted(ROOT.glob(pattern)):
                files = [path] if path.is_file() else sorted(p for p in path.rglob("*") if p.is_file())
                for f in files:
                    rel = f.relative_to(ROOT)
                    if any(part in SKIP_PARTS or part.endswith(".egg-info") for part in rel.parts):
                        continue
                    z.write(f, rel.as_posix())
        z.write(wheel, f"dist/{wheel.name}")
    print(f"wrote {wheel.name} and {out.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
