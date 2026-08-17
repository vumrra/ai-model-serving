#!/usr/bin/env bash
set -euo pipefail

: "${MODEL_REVISION:?MODEL_REVISION must be an immutable Hugging Face commit SHA}"
: "${ENGINE_API_KEY:?ENGINE_API_KEY must protect the public engine proxy}"
[[ "${MODEL_REVISION}" =~ ^[0-9a-f]{40}$ ]] || {
  echo "MODEL_REVISION must be a 40-character lowercase commit SHA" >&2
  exit 64
}

model_id="${MODEL_ID:-Qwen/Qwen3-4B}"
served_model_name="${SERVED_MODEL_NAME:-${model_id}}"

args=(
  python3 -m sglang.launch_server
  --model-path "${model_id}"
  --revision "${MODEL_REVISION}"
  --served-model-name "${served_model_name}"
  --host 127.0.0.1
  --port 8001
  --dtype "${DTYPE:-bfloat16}"
  --context-length "${MAX_MODEL_LEN:-8192}"
  --tp-size "${TENSOR_PARALLEL_SIZE:-1}"
  --mem-fraction-static "${GPU_MEMORY_UTILIZATION:-0.90}"
  --api-key "${ENGINE_API_KEY}"
  --admin-api-key "${ENGINE_ADMIN_API_KEY:-${ENGINE_API_KEY}}"
)

if [[ -n "${SGLANG_EXTRA_ARGS:-}" ]]; then
  # 운영 입력이 아니라 release manifest에서만 관리하는 추가 인자다.
  read -r -a extra_args <<< "${SGLANG_EXTRA_ARGS}"
  args+=("${extra_args[@]}")
fi

"${args[@]}" &
engine_pid=$!
python3 -m uvicorn auth_proxy:app \
  --app-dir /opt/qwen \
  --host 0.0.0.0 \
  --port "${PORT:-8000}" &
proxy_pid=$!

trap 'kill "${engine_pid}" "${proxy_pid}" 2>/dev/null || true' EXIT INT TERM
wait -n "${engine_pid}" "${proxy_pid}"
