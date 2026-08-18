#!/usr/bin/env bash
set -euo pipefail

: "${MODEL_ID:?MODEL_ID is required}"
: "${MODEL_REVISION:?MODEL_REVISION is required}"
[[ "${MODEL_REVISION}" =~ ^[0-9a-f]{40}$ ]] || {
  echo "MODEL_REVISION must be an immutable 40-character lowercase commit SHA" >&2
  exit 64
}

model_path="$({
  python - "${MODEL_ID}" "${MODEL_REVISION}" <<'PY'
import sys
from huggingface_hub import snapshot_download

print(snapshot_download(repo_id=sys.argv[1], revision=sys.argv[2]))
PY
})"

exec python -m mlx_lm.server \
  --model "${model_path}" \
  --host 0.0.0.0 \
  --port "${PORT:-8000}" \
  --chat-template-args "{\"enable_thinking\":${ENABLE_THINKING:-true}}"
