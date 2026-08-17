ARG PYTHON_IMAGE=python:3.11.9-slim-bookworm
FROM ${PYTHON_IMAGE}

ARG TORCH_VERSION=2.7.1
ARG TORCH_INDEX_URL=https://download.pytorch.org/whl/cu128

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    MODEL_ID=Qwen/Qwen3-0.6B \
    MODEL_DEVICE=auto \
    MODEL_DTYPE=auto \
    MAX_CONCURRENT_REQUESTS=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./requirements.txt
RUN python -m pip install --index-url "${TORCH_INDEX_URL}" "torch==${TORCH_VERSION}" \
    && python -m pip install -r requirements.txt

COPY app.py ./engines/transformers/app.py
COPY __init__.py ./engines/transformers/__init__.py
RUN touch ./engines/__init__.py

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --start-period=180s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/readyz', timeout=2)"

CMD ["uvicorn", "engines.transformers.app:app", "--host", "0.0.0.0", "--port", "8000"]
