# Qwen Serving Lab

Qwen 모델을 API로 제공하고, Transformers·vLLM·SGLang을 같은 조건에서 비교한 뒤 실제 배포와 롤백까지 경험하는 프로젝트입니다.

현재 첫 번째 수직 슬라이스는 GPU 없이 실행됩니다.

```text
사용자 요청 → FastAPI Gateway → Mock Engine → JSON 또는 SSE 답변
```

이후 Mock Engine만 Qwen/vLLM/SGLang으로 교체하며 외부 API 계약은 유지합니다.

최종 결과는 맞습니다. 사용자가 문장을 보내면 Gateway가 선택된 Qwen 엔진에 요청하고,
일반 JSON 또는 토큰 단위 SSE로 답변을 반환합니다.

## 구현 로드맵

| 일차 | 상태 | 구현 결과 | 배우는 핵심 |
| --- | --- | --- | --- |
| 1일 | 완료 | Mock Engine과 Gateway 수직 슬라이스 | FastAPI, 요청/응답, async |
| 2일 | 완료 | Transformers CPU smoke와 계약 테스트 | tokenizer, generation, 테스트 |
| 3일 | 완료 | llama.cpp·MLX-LM 로컬 실행 | 양자화, GGUF, Metal |
| 4일 | 로컬 완료 | vLLM·SGLang GPU 이미지와 L40S smoke | CUDA, 엔진 실행 옵션 |
| 5일 | 로컬 구현 | Kind와 KServe Standard Mode | Kubernetes, CRD, Helm |
| 6일 | 일부 구현 | MLX CPU `ServingRuntime`·`InferenceService` | 선언형 모델 서빙, readiness |
| 7일 | 예정 | 동일 조건 엔진 비교 | TTFT, TPOT, p95, throughput, GPU 메모리 |
| 8일 | 예정 | Argo CD GitOps와 관측성 | image digest, Helm, Prometheus, Grafana |
| 9일 | 예정 | 확장·canary·rollback·장애/비용 실험 | KEDA, Knative 선택, 운영 판단 |

기본 운영 경로는 KServe Standard Mode입니다. Knative는 모델 cold start를 감수하고
scale-to-zero와 revision 기반 트래픽 관리가 필요할 때만 선택합니다. 상세한 도구 역할과
선택 기준은 [Kubernetes 모델 서빙 가이드](docs/kubernetes-serving.md)에 정리했습니다.
[최종 아키텍처 HTML](docs/ai-serving-architecture.html)에서는 API와 CI/CD 흐름을 함께 볼 수 있습니다.

4일차 코드는 완료됐으며 실제 L40S smoke만 RunPod 인스턴스를 할당한 뒤 실행합니다.
현재 GitHub Actions는 역할이 겹치지 않는 세 workflow만 둡니다.

| Workflow | 실행 시점 | 역할 |
| --- | --- | --- |
| `ci` | push, pull request | lint, typecheck, test, Gateway image build |
| `gpu-runtime` | 수동 실행 | 선택한 엔진 image build, L40S JSON·SSE smoke, Pod 삭제 |
| `cleanup-runpod` | 30분마다 | 중단된 workflow가 남긴 만료 Pod 삭제 |

로컬에서는 클라우드 자원을 만들지 않고 구조와 테스트만 검증합니다.

```bash
task gpu-verify
```

Task가 없다면 최소 구조 검증을 직접 실행합니다.

```bash
uv run python scripts/verify_gpu_workflow.py
```

실제 실행에 필요한 secret과 `gpu-runtime` 입력값은
[CI/CD 연결 체크리스트](docs/cicd-setup.md)에 정리했습니다.

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

```bash
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

```bash
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

### 로컬 Chat UI

실행할 엔진 하나 또는 둘을 먼저 켜고 UI Gateway를 실행합니다.

```bash
# 터미널 1
task llama-serve

# 터미널 2: MLX-LM도 함께 비교할 때만 실행
task mlx-serve

# 터미널 3
task chat-ui
```

브라우저에서 [http://127.0.0.1:8000](http://127.0.0.1:8000)을 열고 llama.cpp 또는 MLX-LM을
선택합니다. 모델 응답은 SSE로 들어오는 즉시 화면에 표시됩니다. 기본 로컬 API key는
`local-public-key`입니다. UI는 `CHAT_UI_ENABLED=true`일 때만 노출됩니다.

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

## Kind + KServe + MLX-LM

Apple Silicon Mac의 Docker 안에 Kind cluster를 만들고, KServe Standard Mode에서
`mlx-community/Qwen3-4B-4bit`을 Linux CPU로 실행합니다. Docker Desktop에 CPU 4개와
메모리 10GB 이상을 할당하는 것을 권장합니다.

```bash
brew install kind
task kind-up
task kserve-install
task mlx-kind-image
task kserve-deploy
```

첫 배포는 image 설치와 약 2.5GB 모델 다운로드 때문에 오래 걸릴 수 있습니다. 배포 상태는
다음 명령으로 확인합니다.

```bash
kubectl -n qwen-serving get inferenceservice,pod
kubectl -n qwen-serving logs -f deployment/qwen-mlx-predictor
```

KServe 서비스를 전용 포트 8005로 연결한 다음 UI를 실행합니다. 네이티브 MLX-LM의 8004와
겹치지 않으므로 한 화면에서 둘을 비교할 수 있습니다.

```bash
# 터미널 1
task kserve-forward

# 터미널 2
task chat-ui
```

브라우저에서 `http://127.0.0.1:8000`을 열고 `KServe · MLX-LM`을 선택합니다. 흐름은
`Chat UI → Gateway → localhost:8005 → port-forward → KServe → MLX-LM`입니다.
cluster 없이 chart만 검사하려면 `task kserve-verify`, 실습이 끝났으면 `task kind-down`을
실행합니다. Linux CPU의 4B 추론은 첫 token에 수분이 걸릴 수 있어 UI Gateway timeout은
이 로컬 실습에서 10분으로 설정합니다. 실제 성능 실험은 GPU의 vLLM·SGLang에서 진행합니다.

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
engines/       Transformers baseline, MLX CPU, vLLM, SGLang
benchmarks/    동일 workload의 TTFT·E2E·성공률 측정
evals/         답변 품질 회귀 검사
deploy/        RunPod, Cloud Run, Kind/KServe 설정
.github/       CI, image build, staging, 승격, rollback, cleanup
ops/           metric dashboard와 alert 예시
releases/      immutable release manifest schema
```

실제 계정 연결에 필요한 secret과 workflow 순서는
[docs/cicd-setup.md](docs/cicd-setup.md)에 정리했습니다.
Kubernetes·KServe·Argo CD·Knative의 역할과 선택 기준은
[docs/kubernetes-serving.md](docs/kubernetes-serving.md)를 참고합니다.
현재 로컬 Kind·KServe·MLX-LM의 구조와 실행 흐름은
[docs/local-kind-kserve-mlx.md](docs/local-kind-kserve-mlx.md)에 자세히 정리했습니다.
모델·양자화·thinking과 생성·엔진 옵션은
[docs/model-and-inference-options.md](docs/model-and-inference-options.md)에 정리했습니다.

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
- KServe가 vLLM·SGLang을 동일한 GPU 조건으로 배포한다.
- Argo CD가 Git에 고정된 image digest와 manifest를 클러스터에 반영한다.
- Knative 사용 여부를 cold start와 scale-to-zero 요구로 판단할 수 있다.
