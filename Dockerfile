FROM python:3.12-slim AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    POETRY_VERSION=1.8.4 \
    POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_CREATE=false

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir poetry==$POETRY_VERSION
WORKDIR /build

COPY pyproject.toml poetry.lock ./
RUN poetry export --without-hashes --format requirements.txt > requirements.txt
RUN pip wheel --no-cache-dir --wheel-dir /wheels -r requirements.txt

FROM python:3.12-slim AS runtime

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/* \
    && addgroup --system --gid 1000 iatb \
    && adduser --system --uid 1000 --ingroup iatb iatb

WORKDIR /app

COPY --from=builder /wheels /wheels
COPY --from=builder /build/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir /wheels/* \
    && rm -rf /wheels /tmp/requirements.txt \
    && mkdir -p /app/data /app/logs \
    && chown -R iatb:iatb /app

COPY src/ /app/src/
COPY config/ /app/config/
COPY .env.example /app/.env.example
COPY scripts/docker-healthcheck.py /app/scripts/docker-healthcheck.py

ENV PYTHONPATH=/app/src

USER iatb

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["python", "/app/scripts/docker-healthcheck.py"]

CMD ["python", "-m", "iatb.core.runtime"]
