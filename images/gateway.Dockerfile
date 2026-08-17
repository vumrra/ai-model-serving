ARG PYTHON_IMAGE=python:3.11-slim@sha256:9c900dea9e8fb7e16277c179b555cc72d29a352dbc33cff48ad5a0412fd5bfc7
FROM ${PYTHON_IMAGE} AS builder

ARG UV_VERSION=0.12.5
RUN pip install --no-cache-dir "uv==${UV_VERSION}"
WORKDIR /app
COPY pyproject.toml uv.lock* ./
RUN uv sync --frozen --no-dev || uv sync --no-dev

FROM ${PYTHON_IMAGE}
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY apps /app/apps
USER 65532:65532
CMD ["sh", "-c", "uvicorn apps.gateway.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
