# CI/CD 연결 체크리스트

4일차는 GitHub Actions에서 GPU runtime image를 만들고 RunPod L40S에서 smoke하는 단계다.
로컬 검증은 RunPod API를 호출하지 않으므로 계정이나 GPU 인스턴스 없이 실행할 수 있다.

## 현재 Workflow

| 이름 | 트리거 | 책임 |
| --- | --- | --- |
| `ci` | push, pull request | Python 검증과 Gateway image build |
| `gpu-runtime` | 수동 | 엔진 image build, L40S smoke, 증거 저장, Pod 종료 |
| `cleanup-runpod` | 30분 schedule, 수동 | 만료된 프로젝트 Pod 정리 |

이미지 build와 GPU smoke는 같은 workflow에 둔다. build 결과 digest를 다음 workflow로 전달할
필요가 없고, 선택한 엔진 하나만 실행하므로 비용과 실패 지점을 확인하기 쉽다.

## 로컬 검증

```bash
task gpu-verify
```

이 명령은 workflow, RunPod payload/readiness와 JSON·SSE workload만 검사한다. Docker image를
내려받거나 Pod를 생성하지 않는다.

## GitHub Environment

Repository의 `Settings → Environments`에서 `gpu-staging`을 만든다. required reviewer를
지정하면 승인 전에는 image build와 GPU 생성이 시작되지 않는다.

### Secrets

| 이름 | 용도 |
| --- | --- |
| `RUNPOD_API_KEY` | Pod 생성·조회·삭제 |
| `RUNPOD_REGISTRY_AUTH_ID` | private GHCR image를 당겨올 RunPod registry credential ID |
| `ENGINE_API_KEY` | smoke client와 engine auth proxy가 공유하는 key |

RunPod Secrets에도 `ENGINE_API_KEY`와 같은 값을 `qwen_engine_api_key`라는 이름으로 저장한다.
Pod 생성 payload에는 실제 값 대신 `{{ RUNPOD_SECRET_qwen_engine_api_key }}`만 들어간다.

### Variables

| 이름 | 기본값 | 용도 |
| --- | ---: | --- |
| `RUNPOD_ENGINE_SECRET_NAME` | `qwen_engine_api_key` | RunPod에 저장한 engine key 이름 |
| `RUNPOD_MAX_HOURLY_RATE` | `1.25` | 허용하는 GPU 시간당 달러 상한 |
| `RUNPOD_JOB_BUDGET` | `5.00` | 45분 smoke 한 번의 달러 상한 |

## GPU Runtime 실행

GitHub의 `Actions → gpu-runtime → Run workflow`에서 입력한다.

| 입력 | 예시 형식 | 설명 |
| --- | --- | --- |
| `engine` | `vllm` | `vllm` 또는 `sglang` 중 하나 |
| `base_image` | `vllm/vllm-openai:<version>@sha256:<64-hex>` | 검증한 upstream image와 digest |
| `engine_version` | upstream image의 버전 | smoke artifact에 남길 엔진 버전 |

SGLang은 `lmsysorg/sglang:<version>@sha256:<64-hex>` 형식을 사용한다. tag만 입력하면
Dockerfile 검증에서 실패한다. vLLM과 SGLang은 각각 workflow를 실행하며 동시에 두 GPU를
점유하지 않는다.

실행 순서는 다음과 같다.

1. `qwen-vllm` 또는 `qwen-sglang` image를 GHCR에 build하고 push한다.
2. build 결과를 tag가 아닌 digest로 조합한다.
3. Qwen3-4B, BF16, context 8192 조건으로 L40S Pod 하나를 만든다.
4. 인증된 `/v1/models` readiness를 기다린다.
5. JSON 한 건과 SSE 한 건을 실행하고 `gpu-smoke.json`을 저장한다.
6. 성공·실패와 관계없이 Pod를 삭제한다.

artifact `gpu-smoke-<engine>-<run-id>`에는 요청 결과와 secret이 제거된 `pod.json`만 남는다.
workflow가 강제 취소되어 마지막 삭제가 실행되지 않으면 `cleanup-runpod`가 Pod 이름의 만료
시각을 보고 제거한다.

## 이후 일차

5~6일차에 Helm, Kubernetes와 KServe 배포를 추가하고, 7일차에 같은 workload로 성능을
비교한다. staging 승격, Argo CD, rollback workflow는 해당 기능을 구현하는 8~9일차에 만든다.
KServe와 Knative 선택 기준은 [Kubernetes 모델 서빙 가이드](kubernetes-serving.md)를 참고한다.
