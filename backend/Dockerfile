# syntax=docker/dockerfile:1.7
FROM python:3.12.8-slim-bookworm AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /build
COPY backend/pyproject.toml ./
COPY backend/src ./src
RUN python -m pip install --upgrade "pip==24.3.1" "build==1.2.2.post1" && \
    python -m build --wheel --outdir /wheels && \
    python -m pip wheel --wheel-dir /wheels "/wheels/indonesia_wildfire_backend-0.1.0-py3-none-any.whl[rag]"

FROM python:3.12.8-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PATH=/opt/venv/bin:$PATH \
    PYTHONPATH=/app/backend/src

RUN groupadd --system --gid 10001 wildfire && \
    useradd --system --uid 10001 --gid wildfire --home-dir /app --shell /usr/sbin/nologin wildfire && \
    python -m venv /opt/venv

COPY --from=builder /wheels /wheels
RUN python -m pip install --no-cache-dir --no-index --find-links=/wheels \
      "indonesia-wildfire-backend[rag]==0.1.0" && \
    rm -rf /wheels

WORKDIR /app/backend
COPY --chown=wildfire:wildfire backend/src ./src
COPY --chown=wildfire:wildfire backend/resources ./resources
COPY --chown=wildfire:wildfire backend/scripts ./scripts
COPY --chown=wildfire:wildfire data/contracts /app/data/contracts
COPY --chown=wildfire:wildfire data/scripts /app/data/scripts

RUN mkdir -p /app/backend/data /app/ingest /tmp/wildfire && \
    chown -R wildfire:wildfire /app/backend/data /app/ingest /tmp/wildfire

USER 10001:10001
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=3).read()"]

CMD ["uvicorn", "wildfire_api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
