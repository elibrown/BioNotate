FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    ASTROHEALTH_DB=/app/storage/astrohealth.db

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential cmake \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app/backend
COPY backend/requirements.txt ./requirements.txt
COPY backend/vendor ./vendor
RUN python -m pip install -r requirements.txt

RUN groupadd --gid 10001 astro \
    && useradd --uid 10001 --gid astro --create-home astro \
    && mkdir -p /app/backend/uploads /app/storage \
    && chown astro:astro /app/backend/uploads /app/storage

COPY backend/app ./app
COPY frontend /app/frontend
# Include only public demo fixtures, never private/captured health data.
COPY data/shared/astrohealth.sqlite3 /app/data/shared/astrohealth.sqlite3
COPY data/astronauts.json data/metrics.json data/predictions.json data/rules.json /app/data/

USER astro
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=3)" || exit 1

CMD ["sh", "-c", "python -m app.db_snapshot init && exec python -m uvicorn app.main:app --host 0.0.0.0 --port 8000"]
