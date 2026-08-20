# Windows GTX 1660 GPU 운영 구조

이 문서는 개인 Windows 데스크탑을 Qwen Serving Lab의 GPU 배포 대상으로 사용하는 목표 구조와
운영 절차를 정의합니다. 현재 구현된 환경은 Apple Silicon의 Kind/KServe CPU 경로이며, 이 문서의
Windows GPU, Argo CD, 외부 공개 구성은 다음 구현 단계입니다.

## 결정 요약

| 항목 | 선택 | 이유 |
| --- | --- | --- |
| Host | Windows 11 | 기존 개인 데스크탑 사용 |
| Linux 환경 | WSL2 Ubuntu | vLLM은 Linux 환경을 기준으로 지원 |
| GPU | GTX 1660 6GB | 보유 장비로 반복 실험 비용 제거 |
| 로컬 Kubernetes | Minikube Docker driver | Windows/WSL2에서 GPU 전달 경로가 Kind보다 명확함 |
| 배포 모드 | KServe Standard Mode | 단일 GPU 상시 replica, Knative와 Istio 불필요 |
| 모델 | Qwen3-1.7B | 6GB VRAM에서 비양자화 모델을 우선 검증 |
| dtype | float16 | GTX 1660은 BF16 대상 GPU가 아님 |
| CD | Argo CD pull-based GitOps | 집 Kubernetes API를 GitHub에 공개하지 않음 |
| Registry | GHCR | GitHub Actions의 `GITHUB_TOKEN`으로 image 게시 |
| 외부 진입점 | Cloudflare Tunnel 또는 사설망 | Gateway만 노출하고 vLLM과 관리 UI는 비공개 |
| Rollback | Git revert + Argo CD sync | 단일 GPU라 blue/green 동시 실행이 어려움 |

이 환경은 GKE의 축소판이지만 고가용성 production은 아닙니다. PC 전원, Windows 재부팅, 단일
GPU 장애가 곧 서비스 중단으로 이어집니다. 목표는 GPU 추론, Kubernetes, KServe, GitOps와
운영 판단을 실제로 경험하는 것입니다.

## 전체 구조

```text
Developer
  │ push / pull request
  ▼
GitHub repository
  ├── application source
  ├── Helm chart
  ├── environment values
  └── GitHub Actions
       ├── lint / typecheck / test
       ├── Helm render validation
       ├── linux/amd64 image build
       ├── vulnerability scan
       └── Gateway image → GHCR@sha256
                            │
                            │ GitOps values update
                            ▼
Windows 11
└── WSL2 Ubuntu
    └── Minikube
        ├── Argo CD
        │   └── Git 상태를 pull하고 자동 동기화
        ├── NVIDIA GPU runtime
        ├── KServe Standard Mode
        │   └── vLLM CUDA Pod
        │       └── Qwen3-1.7B FP16
        ├── FastAPI Gateway
        ├── Open WebUI
        └── Prometheus / Grafana
```

API 요청 경로는 다음과 같습니다.

```text
Client
  → Cloudflare Tunnel 또는 localhost
  → FastAPI Gateway
  → qwen-vllm-gpu-predictor Service
  → vLLM CUDA Pod
  → Qwen3-1.7B
```

Gateway만 외부에 공개합니다. Kubernetes API, Argo CD, KServe predictor, Prometheus와 Grafana는
외부에 직접 공개하지 않습니다.

## GKE 설계와의 대응 관계

| GKE 목표 구성 | Windows 데스크탑 구성 |
| --- | --- |
| GKE cluster | WSL2 Minikube cluster |
| 관리형 NVIDIA GPU node | GTX 1660 한 장 |
| Artifact Registry | GHCR |
| Persistent Disk | Minikube local PVC |
| Cloud Load Balancer | Cloudflare Tunnel 또는 로컬 port-forward |
| Workload Identity | 제한된 Kubernetes Secret |
| Cloud Monitoring | Prometheus와 Grafana |
| Argo CD | 동일하게 사용 |
| KServe | 동일하게 사용 |

Helm chart와 KServe API는 유지합니다. 나중에 GKE로 이동할 때 GPU node pool, StorageClass,
Ingress와 Secret backend만 환경별 values로 교체하는 것이 목표입니다.

## 수동 부트스트랩과 GitOps 경계

처음 한 번은 다음 항목을 수동으로 준비합니다.

```text
Windows NVIDIA driver
→ WSL2 Ubuntu
→ Docker Desktop WSL integration
→ Minikube GPU cluster
→ Argo CD bootstrap
```

Argo CD가 준비된 다음부터 아래 리소스는 Git으로 관리합니다.

```text
platform Application
├── cert-manager
├── KServe CRD와 controller
├── NVIDIA device plugin/runtime 설정
└── 최소 monitoring stack

qwen-serving Application
├── model cache PVC
├── ServingRuntime
├── InferenceService
├── Gateway Deployment와 Service
├── Open WebUI
└── PostSync smoke Job
```

처음에는 저장소 하나에서 `deploy/environments/windows-gpu` 경로를 Argo CD가 감시하게 합니다.
GitOps 변경이 많아지면 application source와 environment repository를 분리합니다.

## CI 흐름

Pull request에서는 외부 GPU를 만들지 않습니다.

```text
ruff check / format check
→ pyright
→ pytest
→ Helm lint / template
→ Kubernetes schema validation
→ linux/amd64 Docker build
→ image vulnerability scan
```

`main` 병합 또는 release tag에서는 다음 작업을 수행합니다.

```text
Gateway image build
→ GHCR push
→ tag가 아닌 image digest 확정
→ windows-gpu values에 digest 반영
→ Git commit 또는 배포 PR 생성
```

vLLM upstream image와 Hugging Face model revision도 변경 가능한 tag나 `main` 대신 digest와 commit
SHA로 고정합니다. GitHub Actions는 배포를 위해 집 Kubernetes API에 접속하지 않습니다.

## Argo CD 흐름

Argo CD는 Git의 원하는 상태와 cluster의 실제 상태를 비교합니다.

```text
Git 변경 감지
→ Helm render
→ Kubernetes sync
→ KServe controller reconcile
→ vLLM Pod startup/readiness
→ PostSync smoke Job
→ Application Healthy 또는 Degraded
```

자동 동기화는 `prune`과 `selfHeal`을 사용하되, Secret과 PVC 삭제 정책은 별도로 보호합니다.
Webhook 없이 기본 polling을 사용하면 Argo CD API를 인터넷에 공개하지 않아도 됩니다.

PostSync Job은 최소한 다음을 검증합니다.

1. `InferenceService` Ready
2. `GET /v1/models`의 모델 이름
3. thinking을 끈 짧은 JSON chat completion
4. 짧은 SSE streaming completion
5. release ID, image digest와 model revision 일치

## GPU ServingRuntime 기준값

첫 기준값은 아래처럼 작게 시작하고 실측으로 조정합니다.

```yaml
modelId: Qwen/Qwen3-1.7B
dtype: float16
maxModelLen: 1024
maxNumSeqs: 1
gpuMemoryUtilization: 0.85
enableThinking: false

resources:
  requests:
    cpu: "2"
    memory: 4Gi
    nvidia.com/gpu: "1"
  limits:
    cpu: "4"
    memory: 8Gi
    nvidia.com/gpu: "1"
```

실제 GPU image는 `linux/amd64` CUDA image를 사용합니다. 현재 Apple Silicon용 ARM64 CPU image를
Windows에 그대로 사용하지 않습니다. GPU 메모리 부족이 발생하면 모델을 CPU로 offload하기보다
context, 동시 요청 수, GPU memory utilization을 먼저 줄입니다.

## 저장소와 캐시

모델 cache와 엔진 compile cache는 PVC에 둡니다.

```text
PVC
├── Hugging Face model cache
└── vLLM compile cache
```

Pod 교체 후에는 재사용되지만 Minikube profile 삭제나 WSL disk 손상에는 안전하지 않습니다.
Git, image digest와 model revision은 복구할 수 있지만 Open WebUI 대화와 benchmark 결과는 별도
backup이 필요합니다.

## Secret 관리

Git에 평문으로 저장하지 않는 값은 다음과 같습니다.

- Gateway public API key
- Hugging Face token
- private GHCR pull credential
- Cloudflare Tunnel token
- Argo CD repository credential

첫 동작 확인은 수동 Kubernetes Secret으로 시작할 수 있습니다. GitOps가 안정화되면
Sealed Secrets 또는 SOPS 같은 암호화된 GitOps 방식을 추가합니다. public repository에 연결한
self-hosted GitHub Actions runner에는 신뢰하지 않는 pull request를 실행하지 않습니다.

## 관측과 알림

16GB RAM 환경에서는 처음부터 대형 logging stack을 올리지 않습니다.

1. Gateway와 vLLM `/metrics`
2. Prometheus의 짧은 retention
3. Grafana dashboard
4. `kubectl logs` 기반 로그 확인
5. 필요할 때 Loki 추가

필수 지표는 다음과 같습니다.

- request success rate와 HTTP 오류율
- TTFT, TPOT, end-to-end latency의 p50/p95
- tokens/sec와 concurrent requests
- GPU utilization, VRAM, power
- KV cache usage
- Pod restart와 model cold-start 시간

## 배포와 rollback

GTX 1660 한 장에서는 이전 모델과 새 모델을 동시에 GPU에 올리기 어렵습니다. 기본 배포 전략은
`Recreate`이며 모델을 교체하는 동안 짧은 중단을 허용합니다.

```text
GitOps values 변경
→ 기존 Pod 종료
→ 새 Pod 시작
→ readiness와 smoke
→ 성공: 유지
→ 실패: Git revert
→ Argo CD가 이전 digest와 revision 복구
```

Argo Rollouts 기반 blue/green과 canary는 GPU가 두 장 이상이거나 GKE GPU node가 여러 개일 때
추가합니다. 단일 GPU에서 형식적인 canary를 넣어도 두 버전을 동시에 실행할 수 없어 이점이
없습니다.

## 장애와 운영 한계

| 상황 | 영향 | 대응 |
| --- | --- | --- |
| Windows 재부팅 | 전체 API 중단 | Docker/WSL/Minikube 기동 확인 후 Argo CD self-heal |
| GPU driver 오류 | vLLM Pod Pending 또는 CrashLoop | WSL `nvidia-smi`, Docker GPU smoke부터 확인 |
| VRAM OOM | model load 또는 request 실패 | context/동시성/메모리 사용률 축소 |
| RAM 부족 | WSL 또는 Kubernetes 불안정 | Open WebUI/monitoring 축소, 32GB upgrade 검토 |
| Minikube 삭제 | local PVC 손실 | 삭제와 stop을 구분하고 중요 데이터 backup |
| 새 release 실패 | API 중단 | Git revert와 cache된 이전 revision 재배포 |
| 인터넷 장애 | 신규 image/model pull 실패 | 이미 받은 image와 model cache 유지 |

## Windows에서 지금 준비할 작업

### 1. Windows PowerShell 관리자 권한

```powershell
wsl --install -d Ubuntu-24.04
wsl --update
wsl --set-default-version 2
```

설치 후 Windows를 재부팅하고 Ubuntu 사용자 계정을 만듭니다.

### 2. NVIDIA driver

Windows에 최신 NVIDIA GeForce driver를 설치합니다. WSL 내부에는 Linux NVIDIA driver를 따로
설치하지 않습니다. Windows driver가 CUDA 기능을 WSL에 전달합니다.

Ubuntu에서 확인합니다.

```bash
nvidia-smi
```

### 3. Docker Desktop

- `Use the WSL 2 based engine` 활성화
- Ubuntu distribution의 WSL Integration 활성화
- Linux container mode 사용
- Docker Desktop 자동 시작 활성화

GPU 전달을 확인합니다.

```bash
docker run --rm --gpus all ubuntu nvidia-smi
```

### 4. WSL resource 상한

Windows 사용자 폴더의 `.wslconfig`에 16GB 전체 RAM 중 최대 10GB 정도를 우선 배정합니다.

```ini
[wsl2]
memory=10GB
swap=4GB
localhostForwarding=true
```

변경 후 PowerShell에서 적용합니다.

```powershell
wsl --shutdown
```

### 5. repository clone

성능을 위해 `/mnt/c`가 아닌 WSL의 Linux filesystem에 clone합니다.

```bash
mkdir -p ~/Project
cd ~/Project
git clone https://github.com/vumrra/ai-model-serving.git qwen-serving-lab
cd qwen-serving-lab
```

여기까지 완료한 뒤 다음 결과를 기록합니다.

```bash
nvidia-smi
docker version
docker info --format '{{json .Runtimes}}'
uname -a
free -h
```

Minikube, KServe와 Argo CD는 GPU가 Docker container까지 정상 전달된 것을 확인한 다음
설치합니다. 첫 검증은 Kubernetes 없이 vLLM CUDA container를 직접 실행하여 드라이버와 모델
문제를 cluster 문제와 분리합니다.

## 참고 자료

- [NVIDIA CUDA on WSL](https://docs.nvidia.com/cuda/wsl-user-guide/)
- [Docker Desktop WSL2 backend](https://docs.docker.com/desktop/features/wsl/)
- [Minikube start GPU option](https://minikube.sigs.k8s.io/docs/commands/start/)
- [vLLM GPU installation](https://docs.vllm.ai/en/stable/getting_started/installation/gpu/)
- [KServe required dependencies](https://kserve.github.io/website/docs/install/dependencies)
- [Argo CD automated sync](https://argo-cd.readthedocs.io/en/stable/user-guide/auto_sync/)
