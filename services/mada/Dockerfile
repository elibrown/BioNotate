FROM python:3.11-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir .

# Knowledge files are data: mount new versions or rebuild the image to update them.
COPY rules.md checks.md ./
COPY scripts ./scripts

ENV RULES_PATH=/app/rules.md CHECKS_PATH=/app/checks.md EMBED_MODEL_DIR=/models/embeddings
EXPOSE 8000
# ONE worker: there is a single model slot; concurrency is handled by the in-process queue.
CMD ["uvicorn", "mada_agent.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
