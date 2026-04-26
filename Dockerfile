#syntax=docker/dockerfile:1.7
# ============================================================================
# IATB Trading Engine — Production-Hardened Multi-Stage Dockerfile
# ============================================================================

# ---------- Stage 1: Build wheels in isolated builder ----------
FROM python:3.12.9-slim-bookworm@sha256:48a11b7ba705fd53bf15248d1f94d36c39549903c5d59edcfa2f3f84126e7b44 AS builder

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
RUN --mount=type=cache,target=/root/.cache/pip \
    poetry export --without-hashes --format requirements.txt > requirements.txt \
    && grep -v '^aion-sentiment==' requirements.txt > requirements-filtered.txt \
    && pip wheel --no-cache-dir --wheel-dir /wheels -r requirements-filtered.txt

# ---------- Stage 2: Minimal runtime image ----------
FROM python:3.12.9-slim-bookworm@sha256:48a11b7ba705fd53bf15248d1f94d36c39549903c5d59edcfa2f3f84126e7b44 AS runtime

LABEL org.opencontainers.image.title="IATB Trading Engine" \
      org.opencontainers.image.description="Interactive Algorithmic Trading Bot — production-hardened container" \
      org.opencontainers.image.source="https://github.com/npmvlKP/IATB-02Apr26" \
      org.opencontainers.image.vendor="IATB" \
      maintainer="IATB Team"

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONHASHSEED=random \
    PYTHONPATH=/app/src

RUN groupadd --system --gid 1000 iatb \
    && useradd --system --uid 1000 --gid iatb --home-dir /app --shell /usr/sbin/nologin iatb

WORKDIR /app

COPY --from=builder /wheels /wheels
COPY --from=builder /build/requirements.txt /tmp/requirements.txt

RUN pip install --no-cache-dir /wheels/* \
    && rm -rf /wheels /tmp/requirements.txt \
    && mkdir -p /app/data /app/logs /app/config \
    && chown -R iatb:iatb /app

COPY --chown=iatb:iatb src/ /app/src/
COPY --chown=iatb:iatb config/ /app/config/
COPY --chown=iatb:iatb scripts/docker-healthcheck.py /app/scripts/docker-healthcheck.py

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

USER iatb

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["python", "/app/scripts/docker-healthcheck.py"]

CMD ["python", "-m", "iatb.core.runtime"]
