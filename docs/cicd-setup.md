# CI/CD 연결 체크리스트

코드는 준비되어 있지만 실제 클라우드 배포에는 본인 계정의 secret과 repository 변수가 필요합니다.

## GitHub Environments

- `gpu-staging`: GPU 생성과 staging 배포 승인
- `demo`: 공개 트래픽 승격과 rollback 승인

`demo`에는 required reviewer를 설정해 실수로 GPU 비용이 발생하지 않게 합니다.

## GitHub Secrets

| 이름 | 용도 |
| --- | --- |
| `RUNPOD_API_KEY` | Pod 생성·조회·삭제 |
| `RUNPOD_REGISTRY_AUTH_ID` | private GHCR runtime image pull credential ID |
| `ENGINE_API_KEY` | Gateway에서 추론 엔진 호출 |
| `PUBLIC_API_KEY` | 사용자가 공개 API 호출 |
| `GCP_WORKLOAD_IDENTITY_PROVIDER` | GitHub OIDC 인증 |
| `GCP_SERVICE_ACCOUNT` | Artifact Registry·Cloud Run 배포 |

동일한 `ENGINE_API_KEY`, `PUBLIC_API_KEY`를 Google Secret Manager에도 각각
`qwen-engine-api-key`, `qwen-public-api-key` 이름으로 저장합니다.
RunPod Secrets에는 같은 engine key를 `qwen_engine_api_key` 이름으로 저장합니다.
Pod 생성 API에는 값 대신 `{{ RUNPOD_SECRET_qwen_engine_api_key }}` 참조만 전달됩니다.

## GitHub Variables

| 이름 | 예시 |
| --- | --- |
| `MODEL_ID` | `Qwen/Qwen3-4B` |
| `MODEL_REVISION` | `models/manifest.yaml`의 full SHA |
| `SERVING_ENGINE` | `vllm` 또는 `sglang` |
| `BENCHMARK_ENGINE` | 현재 비교할 engine |
| `GAR_REGION` | `asia-northeast3` |
| `GCP_PROJECT_ID` | 본인 GCP project ID |
| `GAR_REPOSITORY` | Gateway image repository |
| `GATEWAY_SERVICE_ACCOUNT` | Secret 두 개만 읽는 Cloud Run runtime identity |
| `RUNPOD_MAX_HOURLY_RATE` | 허용할 GPU 시간당 상한 |
| `RUNPOD_JOB_BUDGET` | 한 benchmark job의 비용 상한 |
| `PROMOTION_MAX_TTFT_MS` | candidate p95 TTFT 상한 |
| `PROMOTION_MAX_E2E_MS` | candidate p95 전체 지연 상한 |

## 실행 순서

1. `ci`: 코드 품질과 계약 테스트
2. `build-images`: runtime·Gateway image 빌드와 release manifest 생성
3. `benchmark-gpu`: 같은 workload로 vLLM·SGLang 측정
4. `deploy-staging`: 새 GPU와 staging Gateway 배포 후 smoke
5. `promote-demo`: tagged candidate에 smoke·품질 평가 후 100% 전환
6. `rollback`: 이전 digest와 model revision으로 engine부터 재생성

RunPod Pod에는 TTL이 이름에 기록되고 scheduled cleanup이 30분마다 만료 Pod를 제거합니다.
