# Qwen Serving Lab

Qwen 모델을 API로 제공하고, Transformers·vLLM·SGLang을 같은 조건에서 비교한 뒤 실제 배포와 롤백까지 경험하는 프로젝트입니다.

현재 첫 번째 수직 슬라이스는 GPU 없이 실행됩니다.

```text
사용자 요청 → FastAPI Gateway → Mock Engine → JSON 또는 SSE 답변
```

이후 Mock Engine만 Qwen/vLLM/SGLang으로 교체하며 외부 API 계약은 유지합니다.

최종 결과는 맞습니다. 사용자가 문장을 보내면 Gateway가 선택된 Qwen 엔진에 요청하고,
일반 JSON 또는 토큰 단위 SSE로 답변을 반환합니다.

## 이번 주 완성 순서

| 일차 | 구현 결과 | 배우는 핵심 |
| --- | --- | --- |
| 1일 | Mock Engine과 Gateway 수직 슬라이스 | FastAPI, 요청/응답, async |
| 2일 | Transformers CPU smoke와 계약 테스트 | tokenizer, generation, 테스트 |
| 3일 | Qwen 4-bit을 llama.cpp·MLX-LM으로 로컬 실행 | 양자화, GGUF, Metal 최적화 |
| 4일 | L40S에서 vLLM·SGLang 동일 조건 비교 | TTFT, p95, throughput, GPU 메모리 |
| 5일 | RunPod + Cloud Run CI/CD | image digest, secret, staging, smoke |
| 6일 | 승격·롤백·장애/비용 실험 | release manifest, 운영 판단 |

KServe는 버린 선택지가 아닙니다. 이번 데모는 엔진 최적화와 API 배포를 먼저 경험하기
위해 Cloud Run과 RunPod로 구성합니다. 이후 여러 모델, 자동 확장, canary rollout을
Kubernetes에서 운영해야 할 때 동일한 엔진 컨테이너를 KServe `InferenceService`로
옮기는 확장 과제로 남깁니다.

## 빠른 시작

Python 3.11 이상과 `uv`가 필요합니다.

```bash
cp .env.example .env
uv sync --dev
uv run --env-file .env python scripts/run_local.py
```

다른 터미널에서 요청합니다.

```bash
curl http://127.0.0.1:8000/v1/chat/completions \
  -H 'Authorization: Bearer local-public-key' \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "qwen3-4b",
    "messages": [{"role": "user", "content": "안녕하세요"}],
    "stream": false
  }'
```

Streaming은 `stream`을 `true`로 바꾸고 `curl -N`을 사용합니다.

## 개발 명령

`Task`가 설치되어 있다면 다음 명령을 사용합니다.

```bash
task dev
task test
task lint
task typecheck
task verify
```

Task가 없다면 각 명령의 `uv run ...` 부분을 직접 실행해도 됩니다.

## Transformers CPU smoke

실제 `Qwen/Qwen3-0.6B`를 `models/manifest.yaml`의 고정 revision으로 내려받아
CPU에서 JSON과 SSE 계약을 확인합니다. 첫 실행에는 약 1.5GB 모델 다운로드가 필요합니다.

```bash
task cpu-smoke
```

API 서버를 직접 실행하려면 다음 명령을 사용합니다. 기본 주소는
`http://127.0.0.1:8002`입니다.

```bash
task cpu-serve
```

## llama.cpp와 MLX-LM 로컬 서버

두 엔진 모두 FastAPI 없이 자체 OpenAI 호환 HTTP 서버를 실행합니다. 모델은
`models/manifest.yaml`의 commit SHA로 고정되며 첫 실행 때 Hugging Face cache로 받습니다.

llama.cpp는 먼저 설치합니다.

```bash
brew install llama.cpp
task llama-serve       # http://127.0.0.1:8003
task llama-smoke       # 서버를 자동으로 시작해 JSON·SSE 검사 후 종료
```

Task가 없다면 다음 명령을 직접 실행합니다.

```bash
uv run --group llama-local python -m scripts.run_local_engine llama_cpp
```

```json
 curl -N http://127.0.0.1:8003/v1/chat/completions \
    -H 'Content-Type: application/json' \
    -d '{
      "model": "qwen3-0.6b",
      "messages": [
        {"role": "user", "content": "서울을 한 문장으로 설명해줘"}
      ],
      "max_tokens": 64,
      "temperature": 0,
      "chat_template_kwargs": {
        "enable_thinking": false
      },
      "stream": true
    }'
```

MLX-LM은 Apple Silicon Mac에서 실행합니다.

```bash
task mlx-serve         # http://127.0.0.1:8004
task mlx-smoke         # 서버를 자동으로 시작해 JSON·SSE 검사 후 종료
```

Task 없이 실행하려면:

```bash
uv run --group mlx-local python -m scripts.run_local_engine mlx_lm
```

```json
 curl -N http://127.0.0.1:8004/v1/chat/completions \
    -H 'Content-Type: application/json' \
    -d '{
      "model": "default_model",
      "messages": [
        {"role": "user", "content": "서울을 한 문장으로 설명해줘"}
      ],
      "max_tokens": 200,
      "temperature": 0,
      "chat_template_kwargs": {
        "enable_thinking": false
      },
      "stream": true
    }'
```

Gateway를 붙일 때는 엔진별 환경 변수만 바꿉니다.

```bash
# llama.cpp
PUBLIC_API_KEY=local-public-key ENGINE_API_KEY= \
ENGINE_BASE_URL=http://127.0.0.1:8003 ENGINE_MODEL_NAME=qwen3-0.6b \
uv run uvicorn apps.gateway.main:app --port 8000

# MLX-LM
PUBLIC_API_KEY=local-public-key ENGINE_API_KEY= \
ENGINE_BASE_URL=http://127.0.0.1:8004 ENGINE_MODEL_NAME=default_model \
uv run uvicorn apps.gateway.main:app --port 8000
```

네이티브 서버는 로컬 개발용이므로 둘 다 `127.0.0.1`에만 바인딩합니다.

`role`은 채팅 템플릿에서 발화자를 구분합니다. `system`은 행동 지침, `user`는 사용자
입력, `assistant`는 이전 모델 답변입니다.

## Python 학습 방법

코드 주석은 꼭 필요한 곳에만 짧게 작성했습니다. 처음 읽을 때는 다음 순서가 좋습니다.

1. `apps/gateway/schemas`에서 요청과 응답 데이터 모양을 확인합니다.
2. `apps/gateway/api/chat.py`에서 HTTP 요청이 들어오는 흐름을 봅니다.
3. `apps/gateway/services/chat_service.py`에서 Gateway와 Engine의 경계를 봅니다.
4. `apps/mock_engine`에서 JSON과 SSE 응답이 어떻게 만들어지는지 확인합니다.
5. `tests/contract`에서 API가 지켜야 하는 규칙을 확인합니다.

문법 설명은 [docs/python-reading-guide.md](docs/python-reading-guide.md)에 따로 정리합니다. 코드 자체는 주석보다 이름과 작은 함수로 읽히도록 유지합니다.

## 구조 읽기

```text
apps/          공개 Gateway와 deterministic Mock Engine
engines/       Transformers baseline, vLLM, SGLang
benchmarks/    동일 workload의 TTFT·E2E·성공률 측정
evals/         답변 품질 회귀 검사
deploy/        RunPod lifecycle과 Cloud Run 배포
.github/       CI, image build, staging, 승격, rollback, cleanup
ops/           metric dashboard와 alert 예시
releases/      immutable release manifest schema
```

실제 계정 연결에 필요한 secret과 workflow 순서는
[docs/cicd-setup.md](docs/cicd-setup.md)에 정리했습니다.

## 프로젝트 원칙

- 모델과 container dependency는 revision/digest로 고정합니다.
- 엔진 비교는 같은 GPU와 같은 workload에서 수행합니다.
- prompt와 API key를 log에 저장하지 않습니다.
- GPU 작업은 TTL과 비용 상한을 둡니다.
- `latest` tag가 아니라 검증한 release digest를 배포합니다.

## 완료 기준

- Mock 환경에서 JSON과 SSE 계약 테스트가 통과한다.
- Transformers, vLLM, SGLang이 같은 API 계약을 제공한다.
- 같은 workload의 TTFT, E2E p95, 성공률을 비교할 수 있다.
- CI가 lint, type check, test, image build를 수행한다.
- staging smoke 이후에만 demo 트래픽을 승격할 수 있다.
- 이전 image와 model revision으로 rollback할 수 있다.
- RunPod 작업에 TTL과 비용 상한이 적용된다.
