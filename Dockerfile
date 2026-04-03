FROM python:3.12-slim AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    POETRY_VERSION=1.8.4

RUN pip install --no-cache-dir poetry==$POETRY_VERSION
WORKDIR /app

COPY pyproject.toml poetry.lock ./
RUN poetry export --without-hashes --format requirements.txt > requirements.txt
RUN pip wheel --no-cache-dir --wheel-dir /wheels -r requirements.txt

FROM python:3.12-slim AS runtime

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN addgroup --system iatb && adduser --system --ingroup iatb iatb
WORKDIR /app

COPY --from=builder /wheels /wheels
COPY --from=builder /app/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir /wheels/* && rm -rf /wheels

COPY src/ /app/src/
COPY config/ /app/config/
COPY .env.example /app/.env.example

USER iatb
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 CMD python -c "import iatb" || exit 1
CMD ["python", "-m", "iatb.core.engine"]
