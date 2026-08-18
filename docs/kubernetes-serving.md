# Kubernetes 모델 서빙 가이드

이 문서는 Qwen Serving Lab에서 Kubernetes, KServe, Argo CD, Knative를 왜 사용하고 언제
선택하는지 정리합니다. 현재는 Kind에 KServe Standard Mode와 MLX-LM CPU runtime을 배포하는
로컬 경로까지 구현되어 있습니다.

## 로컬 구현

```text
브라우저 Chat UI
  → Gateway :8000
  → kubectl port-forward :8005
  → qwen-mlx-predictor Service
  → KServe InferenceService
  → MLX-LM Linux CPU
  → mlx-community/Qwen3-4B-4bit
```

| 파일 | 역할 |
| --- | --- |
| `engines/mlx_cpu/Dockerfile` | Linux CPU용 MLX-LM image |
| `deploy/kubernetes/kind.yaml` | 단일 노드 로컬 cluster |
| `deploy/kubernetes/kserve-values.yaml` | KServe Standard Mode 설정 |
| `charts/qwen-serving/templates/servingruntime.yaml` | MLX-LM 실행 방법 |
| `charts/qwen-serving/templates/inferenceservice.yaml` | 모델 replica와 runtime 연결 |
| `charts/qwen-serving/values-local-mlx-cpu.yaml` | Kind용 로컬 image 설정 |

```bash
task kind-up
task kserve-install
task mlx-kind-image
task kserve-deploy
task kserve-forward
```

MLX의 Linux CPU wheel은 glibc 2.35 이상을 요구하므로 image는 Debian 12 기반 Python을
사용합니다. 모델 revision은 mutable한 `main` 대신 manifest와 같은 commit SHA로 고정합니다.
이 경로는 Kubernetes와 KServe 동작 확인용이며 성능 비교용은 아닙니다. 실제 엔진 비교는
GPU cluster에서 vLLM과 SGLang으로 진행합니다.

## 전체 구조

```text
Git repository
    ↓ Argo CD
Kubernetes cluster
    ↓ KServe
InferenceService
    ↓
GPU Pod
    ↓
vLLM 또는 SGLang
```

외부 API 인증과 요청 제한이 필요하면 기존 Gateway를 앞에 둡니다.

```text
Client → Gateway → KServe InferenceService → vLLM/SGLang → Qwen
```

## 각 도구의 역할

| 도구 | 역할 | 이 프로젝트에서 사용하는 이유 |
| --- | --- | --- |
| Kubernetes | 컨테이너 배치와 복구 | GPU 노드 선택, Pod 재시작, replica 유지 |
| KServe | 모델 서빙용 Kubernetes API | 모델·엔진·GPU 배포를 선언형으로 관리 |
| ServingRuntime | 엔진 실행 방법 | vLLM과 SGLang image·명령·port 정의 |
| InferenceService | 실제 모델 배포 | Qwen 모델, runtime, GPU 수, replica 지정 |
| Argo CD | GitOps 동기화 | Git의 승인된 Helm values와 cluster 상태 일치 |
| Helm | 배포 패키징 | engine·model·GPU 설정을 values로 분리하고 chart로 배포 |
| External Secrets | Secret 동기화 | API key와 registry credential을 Git에서 제외 |
| Prometheus/Grafana | 관측 | TTFT, queue, 오류, GPU와 KV cache 확인 |
| KEDA | 이벤트 기반 확장 | 요청 queue와 엔진 metric으로 replica 조절 |
| Knative | 서버리스 실행 | scale-to-zero, revision, 요청 기반 확장 |

## Helm 선택

Kustomize는 원본 YAML을 patch하는 방식이라 환경이 적을 때 단순합니다. 이 프로젝트는 vLLM과
SGLang, staging과 production 조합을 반복 배포하므로 Helm chart 하나와 환경별 values를
사용합니다. KServe, Argo CD와 Prometheus 설치에도 각 프로젝트의 공식 Helm chart를 사용합니다.

KServe는 추론 엔진이 아닙니다. vLLM과 SGLang이 모델을 실행하고 KServe가 Kubernetes 위에서
두 엔진의 배포와 수명주기를 관리합니다.

## ServingRuntime과 InferenceService

`ServingRuntime`은 실행 방법입니다.

```text
qwen-vllm-runtime  → vLLM image와 실행 명령
qwen-sglang-runtime → SGLang image와 실행 명령
```

`InferenceService`는 그 실행 방법을 사용한 실제 배포입니다.

```text
qwen-vllm  → Qwen3-4B + vLLM runtime + GPU 1장
qwen-sglang → Qwen3-4B + SGLang runtime + GPU 1장
```

두 서비스에 같은 모델 revision, dtype, context length, GPU 수와 workload를 적용해 엔진을
비교합니다.

## Kubernetes를 선택하는 기준

| 상황 | 선택 |
| --- | --- |
| 노트북에서 모델 하나 실행 | llama.cpp 또는 MLX-LM |
| GPU 한 장에서 짧은 실험 | Docker 또는 RunPod Pod |
| 여러 모델·버전·GPU를 반복 운영 | Kubernetes + KServe |
| 장애 자동 복구와 replica 유지 필요 | Kubernetes + KServe |
| Git 승인 내용만 배포해야 함 | Argo CD 추가 |
| queue 기반 GPU 확장이 필요 | KEDA 추가 |
| 요청이 없을 때 Pod를 0개로 줄여야 함 | Knative 검토 |

단일 GPU에서 잠깐 실행하는 서비스라면 Kubernetes는 불필요합니다. 이 프로젝트에서 사용하는
목적은 추론 속도가 아니라 배포, 복구, 확장, 관측, rollback을 학습하는 것입니다.

## KServe 배포 모드 선택

### Standard Mode를 기본으로 사용

다음 상황에서는 Standard Mode를 사용합니다.

- vLLM과 SGLang의 성능을 같은 조건으로 비교할 때
- GPU replica를 항상 1개 이상 유지할 때
- 모델 로딩 시간이 길고 첫 요청 지연이 중요할 때
- 일반 Kubernetes Deployment와 HPA/KEDA 동작을 배우려 할 때

엔진 비교 중에는 replica 1, autoscaling off로 고정합니다. autoscaling을 켜면 Pod 수와 cold
start가 측정값에 섞여 엔진 자체 차이를 판단하기 어렵습니다.

### Knative를 선택하는 상황

다음 조건을 대부분 만족할 때 Knative를 검토합니다.

- 트래픽이 오랫동안 없는 서비스
- GPU Pod를 0개로 내려 비용을 줄여야 하는 서비스
- 첫 요청의 긴 cold start를 허용할 수 있는 서비스
- revision 단위 배포와 요청 기반 확장이 필요한 서비스
- 모델 cache나 빠른 storage로 재기동 시간을 줄일 수 있는 환경

다음 상황에서는 사용하지 않습니다.

- vLLM과 SGLang benchmark
- 항상 트래픽이 있는 서비스
- 첫 token 지연 SLO가 엄격한 서비스
- GPU 노드 생성과 모델 다운로드에 오래 걸리는 환경

Knative가 Pod를 0개로 줄여도 GPU 노드 비용이 자동으로 사라지는 것은 아닙니다. 비용 절감에는
cluster autoscaler가 GPU 노드까지 제거하도록 별도 설정해야 합니다.

## Argo CD와 배포 흐름

배포 manifest와 image tag가 아니라 digest를 Git에 저장합니다.

```text
1. CI가 vLLM 또는 SGLang image를 빌드한다.
2. smoke와 benchmark를 통과한 image digest를 staging values에 기록한다.
3. 변경을 Git에 commit한다.
4. Argo CD가 변경을 감지해 cluster에 적용한다.
5. KServe가 InferenceService 상태를 원하는 상태로 맞춘다.
6. readiness와 API smoke를 통과한 뒤 production values를 갱신한다.
```

Secret 값은 Git에 저장하지 않습니다. External Secrets가 cloud secret manager에서
`ENGINE_API_KEY`, Hugging Face token과 registry credential을 가져오게 합니다.

## Canary와 rollback

처음에는 KServe 또는 Gateway API의 가중치 라우팅 한 가지를 사용합니다.

```text
stable 90% → 이전 image digest
canary 10% → 새 image digest
```

오류율, TTFT p95와 답변 품질이 기준을 통과하면 canary 비율을 올립니다. 실패하면 Git의
production values를 이전 digest로 되돌리고 Argo CD가 동기화하게 합니다.

Argo Rollouts는 처음에는 사용하지 않습니다. KServe가 생성한 Deployment와 소유권이 겹칠 수
있기 때문입니다. 일반 Deployment를 Argo Rollouts가 직접 관리해야 하는 요구가 생길 때만
추가합니다.

## 단계별 운영 실험

1. vLLM과 SGLang Pod를 각각 강제 종료하고 Kubernetes 복구 시간 측정
2. readiness 실패 시 트래픽 차단 확인
3. queue 증가 시 KEDA replica 확장 확인
4. 확장 후 GPU 메모리와 p95 지연 확인
5. stable/canary를 90:10으로 나누고 metric 비교
6. 잘못된 image를 배포한 뒤 이전 digest로 rollback
7. Knative scale-to-zero 후 첫 요청 cold start 측정
8. GPU node scale-down이 실제 비용 감소로 이어지는지 확인

## 선택 순서

이 프로젝트의 기본 선택은 다음과 같습니다.

```text
KServe Standard Mode
→ vLLM·SGLang 비교
→ 엔진 선택
→ Argo CD GitOps
→ Prometheus/Grafana
→ KEDA autoscaling
→ canary/rollback
→ 필요할 때만 Knative
```

최종 엔진으로 vLLM을 선택하고 여러 GPU, KV-cache-aware routing 또는 prefill/decode 분리가
필요해지면 KServe `LLMInferenceService`를 별도 확장 단계로 검토합니다.

## 참고 자료

- [KServe 개요](https://kserve.github.io/website/docs/intro)
- [KServe ServingRuntime](https://kserve.github.io/website/docs/0.16/concepts/resources/servingruntime)
- [KServe LLM autoscaling](https://kserve.github.io/website/docs/model-serving/generative-inference/autoscaling)
- [Argo CD](https://argo-cd.readthedocs.io/)
- [Knative Serving](https://knative.dev/docs/serving/)
