# 로컬 Kind + KServe + MLX-LM 구현 가이드

이 문서는 이 저장소에 구현된 로컬 Kubernetes 모델 서빙 환경이 어떤 구조인지, 명령을
실행하면 내부에서 무엇이 만들어지는지, 요청이 어디를 거쳐 모델에 도달하는지 설명합니다.
마지막에는 이 구성을 GPU 클라우드와 실제 운영 환경으로 확장하는 방법을 정리합니다.

## 1. 한 문장 요약

Docker Desktop 안에 Kind로 단일 노드 Kubernetes cluster를 만들고, KServe가
`mlx-community/Qwen3-4B-4bit`을 실행하는 MLX-LM Pod와 Service를 관리하도록 구성했습니다.

이 구성의 목적은 빠른 로컬 추론이 아니라 다음 운영 흐름을 직접 확인하는 것입니다.

```text
Helm values 변경
  → KServe 사용자 리소스 변경
  → Kubernetes Deployment와 Pod 변경
  → readiness 확인
  → Service를 통한 API 호출
```

## 2. 왜 Pod 하나에 Kubernetes를 사용하는가

Pod 하나만 실행한다면 Kubernetes는 실행 효율 면에서 과한 선택입니다. 단순히 모델을
사용하는 것이 목적이라면 `task mlx-serve`로 MLX-LM을 Mac에서 직접 실행하는 편이 더 빠르고
단순합니다.

이 저장소에서 Kind와 KServe를 함께 사용하는 이유는 모델 실행보다 모델 운영 계층을 학습하기
위해서입니다.

| 목적 | 적합한 실행 방식 |
| --- | --- |
| Mac에서 모델을 빠르게 사용 | MLX-LM 네이티브 실행 |
| 컨테이너 하나를 반복 실행 | Docker 또는 Docker Compose |
| Kubernetes 리소스와 복구 학습 | Kind + KServe |
| 여러 모델·GPU·replica 운영 | 관리형 Kubernetes + KServe |

따라서 두 실행 경로를 구분해야 합니다.

```text
MLX-LM 네이티브 실행 = 모델을 사용하는 경로
Kind + KServe 실행    = 배포와 운영을 학습하는 경로
```

## 3. 전체 구조

```text
Mac
├─ Chat UI / Gateway :8000
├─ kubectl port-forward :8005
└─ Docker Desktop
   └─ qwen-serving-control-plane 컨테이너
      └─ Kind Kubernetes cluster
         ├─ cert-manager namespace
         │  └─ webhook 인증서 관리 Pod
         ├─ kserve namespace
         │  └─ KServe controller Pod
         └─ qwen-serving namespace
            ├─ ServingRuntime/qwen-mlx-cpu
            ├─ InferenceService/qwen-mlx
            ├─ Deployment/qwen-mlx-predictor
            ├─ Service/qwen-mlx-predictor :80
            └─ Pod/qwen-mlx-predictor-...
               └─ kserve-container :8000
                  └─ MLX-LM + Qwen3-4B-4bit
```

Kind의 Kubernetes 노드는 별도 가상머신이 아니라 Docker 컨테이너입니다. Kubernetes가
생성하는 모델 Pod는 이 노드 컨테이너 안에서 실행됩니다.

### 현재 로컬 구성과 운영 목표

현재 Kind에는 모델만 배포합니다. Gateway와 UI는 Mac 프로세스로 실행됩니다.

```text
현재 로컬

Browser
  → Mac Gateway + UI :8000
  → port-forward :8005
  → Kind
     → KServe Service
     → MLX-LM CPU Model Pod
```

운영 환경의 첫 목표는 `GKE Standard + GPU node pool`입니다. GKE는 Google이 Kubernetes
control plane을 관리하는 서비스이고, Standard 모드는 node pool과 Pod 배치를 직접 제어할 수
있습니다. GPU 종류, node 수, taint와 autoscaling을 실험해야 하는 이 프로젝트에 적합합니다.
EKS나 AKS로 바꿔도 Helm과 KServe 구조는 거의 같습니다.

```text
운영 목표

Internet
  → HTTPS Load Balancer / Gateway API
  → Gateway Service
  → Gateway Pod
     ├─ FastAPI 공개 API
     └─ Chat UI
  → KServe 내부 Service
  → GPU Model Pod
     └─ vLLM 또는 SGLang + Qwen

GKE system CPU node pool
  ├─ Gateway Pod
  ├─ KServe Controller
  ├─ cert-manager
  └─ Argo CD

GKE GPU node pool
  └─ Model Pod 1개 이상
```

Gateway와 UI는 하나의 일반 Deployment로 배포하고, 모델 Pod만 KServe가 관리합니다. 외부에는
Gateway만 공개하고 모델 Service는 cluster 내부에 둡니다.

| 구분 | 현재 로컬 | 운영 목표 |
| --- | --- | --- |
| Kubernetes | Kind 단일 Docker node | GKE Standard |
| Gateway/UI | Mac 프로세스 | CPU node의 Gateway Pod |
| 모델 | MLX-LM Linux CPU | vLLM 또는 SGLang GPU |
| 모델 replica | 1 | 1개에서 시작해 확장 |
| 외부 연결 | `kubectl port-forward` | HTTPS Load Balancer/Gateway API |
| image 전달 | `kind load docker-image` | Artifact Registry의 image digest |
| 배포 실행 | 개발자가 `task` 실행 | Argo CD가 Git 변경 동기화 |
| model cache | Pod 임시 저장소 | PVC, object storage 또는 LocalModel |

### Helm chart는 무엇인가

Helm chart는 Kubernetes YAML을 환경별 값으로 생성하는 배포 패키지입니다.

```text
templates/
  ├─ ServingRuntime 틀
  └─ InferenceService 틀

values-local-mlx-cpu.yaml
  → Kind + MLX CPU 리소스 생성

values-staging.yaml / values-production.yaml
  → GKE + GPU 리소스 생성
```

로컬과 운영에서 template을 복사하지 않고 image, 모델, GPU 수, replica 같은 값만 교체하는 것이
핵심입니다. Helm은 Pod를 계속 감시하는 운영 도구가 아니라 YAML을 만들고 cluster에 적용하는
도구입니다. 배포 후 상태 유지는 Kubernetes와 KServe가 담당합니다.

### Argo CD는 무엇인가

Argo CD는 Git에 저장된 Helm chart와 values를 실제 cluster 상태에 맞추는 GitOps
Controller입니다. image를 빌드하지는 않습니다.

```text
개발자 push
  → GitHub Actions 테스트
  → Gateway/vLLM/SGLang image build
  → Artifact Registry push
  → 검증된 image digest를 values에 기록
  → Argo CD가 Git 변경 감지
  → Helm chart rendering
  → Gateway Deployment와 KServe 리소스 적용
  → Kubernetes/KServe가 Pod 교체
```

운영에서 직접 `kubectl edit`하지 않고 Git을 변경합니다. 문제가 생기면 이전 image digest가
들어 있는 Git commit으로 되돌리고 Argo CD가 이전 상태를 다시 적용하게 합니다.

### 확장 순서

```text
1. Kind에 Model Pod만 배포                 ← 현재
2. Kind에 Gateway/UI Pod 추가
3. GKE Standard와 GPU node pool 생성
4. MLX CPU runtime을 vLLM/SGLang으로 교체
5. Gateway API와 HTTPS 연결
6. Argo CD로 Helm chart 자동 동기화
7. Prometheus/Grafana 관측
8. replica 확장, canary, rollback 실험
9. 필요할 때 KEDA 또는 Knative 추가
```

처음부터 모든 기능을 켜지 않습니다. replica 1개와 KServe Standard Mode로 정상 배포를 먼저
확인하고, 실제 요구가 생길 때 autoscaling과 scale-to-zero를 추가합니다.

## 4. 구성 요소별 역할

### Docker Desktop

Kind 노드가 실행될 기반입니다. Mac의 CPU와 메모리를 Linux 컨테이너에 제공합니다.
Qwen3-4B-4bit과 Kubernetes 관리 Pod를 함께 실행하므로 Docker Desktop에 CPU 4개와 메모리
10GB 이상을 할당하는 것을 권장합니다.

### Kind

로컬 Docker 컨테이너로 Kubernetes cluster를 만듭니다. 현재 설정은 control-plane과 worker를
분리하지 않은 단일 노드 구조입니다.

```yaml
kind: Cluster
name: qwen-serving
nodes:
  - role: control-plane
```

실제 클라우드에서는 여러 worker node와 GPU node pool이 있지만, 로컬 학습에는 단일 노드면
충분합니다.

### cert-manager

KServe admission webhook이 사용하는 인증서를 관리합니다. 추론 요청의 API 인증을 담당하는
도구는 아닙니다.

### KServe Controller

`ServingRuntime`과 `InferenceService`를 감시하고 일반 Kubernetes 리소스인 Deployment와
Service를 생성합니다.

```text
ServingRuntime + InferenceService
  → KServe Controller
  → Deployment + Service
  → ReplicaSet
  → Pod
```

KServe는 모델 추론 엔진이 아닙니다. 실제 추론은 Pod 안의 MLX-LM이 수행합니다.

### ServingRuntime

모델을 어떤 컨테이너로 어떻게 실행할지 정의합니다. 현재 runtime은 다음 값을 Pod로
전달합니다.

| 설정 | 현재 값 | 의미 |
| --- | --- | --- |
| image | `qwen-mlx-cpu:local` | Kind에 적재한 Linux CPU image |
| container port | `8000` | MLX-LM HTTP 서버 포트 |
| model format | `huggingface` | Hugging Face snapshot 형식 |
| model ID | `mlx-community/Qwen3-4B-4bit` | 다운로드할 저장소 |
| revision | 고정 commit SHA | 같은 모델 파일 재현 |
| alias | `default_model` | OpenAI API 요청의 모델 이름 |
| thinking | `true` | Qwen thinking 기본값 |

`model format`을 `huggingface`로 지정한 이유는 모델 파일이 Hugging Face snapshot이기
때문입니다. 또한 KServe가 `storageUri` 없는 임의 포맷을 multi-model server로 오인해 model
agent sidecar를 붙이는 것을 방지합니다.

### InferenceService

실제로 배포할 모델과 runtime, replica, 자원을 지정합니다.

```text
InferenceService/qwen-mlx
  ├─ runtime: qwen-mlx-cpu
  ├─ replicas: 1
  ├─ CPU request/limit: 2/4
  ├─ memory request/limit: 4Gi/8Gi
  └─ deployment strategy: Recreate
```

로컬 values에서 `Recreate`를 사용하는 이유는 단일 Kind 노드의 메모리 때문입니다. 기본
RollingUpdate는 기존 4GB Pod와 신규 4GB Pod를 동시에 예약하려고 하므로 새 Pod가
`Insufficient memory` 상태에 빠질 수 있습니다. Recreate는 기존 Pod를 종료한 뒤 새 Pod를
하나만 실행합니다.

실제 운영 cluster에서는 여유 자원이 있다면 RollingUpdate로 되돌리는 것이 일반적입니다.

### MLX-LM CPU Image

`python:3.12-slim-bookworm`에 Linux CPU용 MLX와 MLX-LM을 설치합니다.

컨테이너가 시작되면 다음 순서로 동작합니다.

```text
MODEL_ID와 MODEL_REVISION 검사
  → revision이 40자리 commit SHA인지 검사
  → Hugging Face snapshot 다운로드
  → /models/cache에 저장
  → mlx_lm.server를 0.0.0.0:8000에서 실행
```

`main` 같은 mutable revision을 허용하지 않으므로 나중에 같은 설정으로 배포해도 모델 내용이
바뀌지 않습니다.

### Kubernetes Service

Pod 이름과 IP는 재배포할 때 바뀝니다. `qwen-mlx-predictor` Service는 고정된 이름과 cluster
IP를 제공하고 현재 Ready 상태인 Pod로 요청을 전달합니다.

```text
Service :80 → Pod :8000
```

### Gateway와 Chat UI

Gateway는 추론을 수행하지 않습니다. 브라우저용 UI를 제공하고 사용자가 선택한 로컬 엔진으로
요청을 전달합니다.

```text
llama.cpp         → localhost:8003
MLX-LM 네이티브  → localhost:8004
KServe · MLX-LM  → localhost:8005
```

KServe API를 `curl`로 직접 사용할 때는 Gateway가 필요 없습니다. Chat UI, API key, 요청 제한,
공통 오류 형식이 필요할 때만 Gateway를 사용합니다.

## 5. 파일별 역할

로컬 Kubernetes 구성과 직접 관련된 파일만 표시하면 다음과 같습니다.

```text
ai-model-serving/
├─ deploy/
│  └─ kubernetes/
│     ├─ kind.yaml
│     │  # Docker 안에 단일 노드 Kind cluster를 생성
│     └─ kserve-values.yaml
│        # KServe를 Knative 없는 Standard Mode로 설치
│
├─ engines/
│  └─ mlx_cpu/
│     ├─ Dockerfile
│     │  # Linux CPU용 MLX와 MLX-LM image를 빌드
│     └─ entrypoint.sh
│        # 고정 revision 모델을 다운로드하고 MLX-LM :8000 실행
│
├─ charts/
│  └─ qwen-serving/
│     ├─ Chart.yaml
│     │  # qwen-serving Helm chart의 이름과 버전
│     ├─ values.yaml
│     │  # 모델 ID, revision, runtime image, CPU와 메모리 기본값
│     ├─ values-local-mlx-cpu.yaml
│     │  # Kind에서는 local image와 Recreate 배포 전략을 사용
│     └─ templates/
│        ├─ servingruntime.yaml
│        │  # KServe에 MLX-LM 컨테이너 실행 방법을 등록
│        └─ inferenceservice.yaml
│           # runtime, 모델, replica와 자원을 연결해 실제 서비스 배포
│
├─ apps/
│  └─ gateway/
│     ├─ main.py
│     │  # KServe port-forward :8005를 UI 선택 엔진으로 연결
│     └─ chat.html
│        # llama.cpp, MLX-LM, KServe MLX-LM 선택 화면
│
├─ tests/
│  ├─ unit/test_kubernetes_chart.py
│  │  # Helm 결과와 immutable model revision을 검사
│  └─ contract/test_chat_ui.py
│     # UI가 KServe 엔진을 올바른 포트와 모델명으로 호출하는지 검사
│
└─ Taskfile.yml
   # kind-up → kserve-install → image build → deploy → port-forward 명령
```

파일이 연결되는 순서는 다음과 같습니다.

```text
kind.yaml
  → Kubernetes cluster 생성

kserve-values.yaml
  → KServe Controller 설치

Dockerfile + entrypoint.sh
  → MLX-LM 실행 image 생성

values*.yaml + templates/*.yaml
  → ServingRuntime + InferenceService 생성

KServe Controller
  → Deployment + Service + Model Pod 생성

Gateway main.py + chat.html
  → 사용자가 Model Pod API를 UI에서 호출
```

## 6. 처음부터 실행하기

### 요구 사항

```bash
docker --version
kind --version
kubectl version --client
helm version
task --version
```

Mac에 Kind가 없다면 설치합니다.

```bash
brew install kind
```

Docker Desktop은 먼저 실행되어 있어야 합니다.

### 1단계: Kind cluster 생성

```bash
task kind-up
```

내부적으로 다음 명령을 실행합니다.

```bash
kind create cluster --config deploy/kubernetes/kind.yaml
```

확인:

```bash
kubectl cluster-info --context kind-qwen-serving
kubectl get nodes
```

### 2단계: KServe 설치

```bash
task kserve-install
```

다음 구성 요소가 Helm으로 설치됩니다.

1. cert-manager
2. KServe CRD
3. KServe Controller와 관련 리소스

Knative는 설치하지 않습니다. 현재 배포는 일반 Deployment와 Service를 사용하는 KServe
Standard Mode입니다.

확인:

```bash
kubectl get pods -n cert-manager
kubectl get pods -n kserve
kubectl get crd | grep kserve
```

### 3단계: MLX CPU image 빌드와 적재

```bash
task mlx-kind-image
```

명령은 두 작업을 수행합니다.

```text
Docker로 qwen-mlx-cpu:local image 빌드
  → kind load docker-image로 노드 containerd에 복사
```

`imagePullPolicy: IfNotPresent`이므로 Kubernetes는 외부 registry에서 이 image를 찾지 않고 Kind
노드에 적재된 image를 사용합니다.

### 4단계: 모델 배포

```bash
task kserve-deploy
```

Helm이 `ServingRuntime`과 `InferenceService`를 적용하고, KServe가 Deployment와 Service를
생성합니다. 이후 명령은 Deployment rollout과 `InferenceService Ready=True`를 기다립니다.

첫 실행에는 약 2GB 이상의 모델을 다운로드하므로 시간이 걸립니다.

확인:

```bash
kubectl -n qwen-serving get servingruntime
kubectl -n qwen-serving get inferenceservice
kubectl -n qwen-serving get deployment,service,pod
```

정상 상태의 핵심은 다음과 같습니다.

```text
InferenceService READY=True
Deployment READY=1/1
Pod READY=1/1, STATUS=Running
```

### 5단계: 로그 확인

```bash
kubectl -n qwen-serving logs -f deployment/qwen-mlx-predictor
```

정상 흐름에서는 모델 파일 다운로드 후 다음과 같은 단계가 보입니다.

```text
Fetching files
→ Starting httpd at 0.0.0.0 on port 8000
→ GET /v1/models 200
```

### 6단계: API 연결

Kubernetes의 ClusterIP Service는 Mac에서 직접 접근할 수 없으므로 포트포워딩합니다.

```bash
task kserve-forward
```

이 터미널은 계속 실행해 둡니다.

```text
Mac localhost:8005
  → kubectl port-forward
  → Service/qwen-mlx-predictor:80
  → Pod:8000
```

readiness 확인:

```bash
curl http://127.0.0.1:8005/v1/models
```

Gateway 없이 직접 추론 요청:

```bash
curl -N http://127.0.0.1:8005/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "default_model",
    "messages": [
      {"role": "user", "content": "서울을 한 문장으로 설명해줘"}
    ],
    "max_tokens": 32,
    "temperature": 0,
    "chat_template_kwargs": {
      "enable_thinking": false
    },
    "stream": true
  }'
```

Linux CPU에서 4B 모델을 실행하므로 첫 token까지 수분이 걸릴 수 있습니다. 이 경로는 성능
측정용이 아니라 Kubernetes 배포와 API 연결 확인용입니다.

### 7단계: Chat UI 연결

포트포워딩을 유지한 상태에서 다른 터미널을 엽니다.

```bash
task chat-ui
```

브라우저에서 다음 주소를 엽니다.

```text
http://127.0.0.1:8000
```

엔진 목록에서 `KServe · MLX-LM · 8005`를 선택합니다. KServe CPU 추론이 느리므로 이 실습의
Gateway upstream timeout은 10분입니다.

## 7. 요청이 처리되는 과정

### KServe API 직접 호출

```text
curl
  → localhost:8005
  → kubectl port-forward
  → qwen-mlx-predictor Service:80
  → Ready 상태의 qwen-mlx-predictor Pod:8000
  → mlx_lm.server
  → Qwen3-4B-4bit
  → JSON 또는 SSE 응답
```

이 경로는 엔진 자체의 API와 지연을 확인할 때 사용합니다.

### Chat UI 호출

```text
Browser
  → Gateway:8000
  → /ui/chat/completions?engine=kserve_mlx
  → localhost:8005
  → port-forward
  → KServe Service
  → MLX-LM Pod
  → SSE 응답
  → Gateway가 Browser로 전달
```

이 경로에는 Gateway 처리 시간이 추가되므로 엔진 성능 benchmark에는 사용하지 않습니다.

## 8. 배포 변경이 반영되는 과정

예를 들어 `values.yaml`에서 CPU나 모델 revision을 변경하고 `task kserve-deploy`를 다시
실행하면 다음 과정이 일어납니다.

```text
Helm values 변경
  → ServingRuntime 또는 InferenceService spec 변경
  → KServe Controller가 변경 감지
  → qwen-mlx-predictor Deployment 변경
  → 기존 Pod 종료
  → 새 Pod 생성
  → 모델 다운로드와 MLX-LM 시작
  → startup probe 성공
  → readiness probe 성공
  → InferenceService Ready=True
```

KServe가 만든 Deployment를 `kubectl edit deployment`로 직접 수정하면 Controller가 다시 원래
상태로 되돌릴 수 있습니다. 영구 변경은 Helm values 또는 template에서 해야 합니다.

## 9. Probe와 장애 복구

MLX-LM의 `/v1/models`를 startup probe와 readiness probe에서 사용합니다.

### Startup probe

모델 다운로드와 로딩이 끝날 때까지 기다립니다. 10초 간격으로 최대 180번 확인하므로 최대
약 30분의 시작 시간을 허용합니다. 이 시간 안에 성공하지 못하면 Kubernetes가 컨테이너를
재시작합니다.

### Readiness probe

서버가 요청을 받을 수 있는지 10초마다 검사합니다. 실패한 Pod는 실행 중이더라도 Service의
요청 대상에서 제외됩니다.

### Pod 복구 실험

현재 Pod 이름을 확인하고 삭제할 수 있습니다.

```bash
kubectl -n qwen-serving get pods
kubectl -n qwen-serving delete pod -l serving.kserve.io/inferenceservice=qwen-mlx
kubectl -n qwen-serving get pods -w
```

Deployment가 replica 1개를 유지하므로 새 Pod가 자동으로 생성됩니다. 다만 현재 모델 cache는
Pod의 임시 저장소에 있으므로 모델을 다시 다운로드합니다.

## 10. 현재 구성의 한계

| 한계 | 현재 영향 | 확장 방법 |
| --- | --- | --- |
| 단일 Kind 노드 | 노드 장애와 분산 배치 실험 불가 | 다중 노드 또는 cloud cluster |
| CPU 4B 추론 | 첫 token과 생성 속도가 매우 느림 | Mac 네이티브 MLX 또는 GPU engine |
| replica 1개 | 무중단 교체와 부하 분산 불가 | GPU 여유 자원 확보 후 replica 증가 |
| Recreate 배포 | 교체 중 서비스 중단 | RollingUpdate와 여유 node 사용 |
| Pod 임시 model cache | Pod 교체 때 재다운로드 | PVC, hostPath 또는 KServe LocalModel |
| port-forward | 개발 터미널이 끊기면 접근 불가 | Gateway API, Ingress 또는 LoadBalancer |
| 공개 HF 다운로드 | rate limit 가능 | Kubernetes Secret으로 `HF_TOKEN` 전달 |
| API 인증 없음 | engine port를 공개하면 위험 | Gateway 인증 또는 service mesh 정책 |
| autoscaling 없음 | 요청량에 따른 확장 불가 | HPA/KEDA, 필요할 때 Knative |

## 11. 자주 발생하는 문제

### `kind: command not found`

```bash
brew install kind
```

### Docker daemon에 연결할 수 없음

Docker Desktop을 실행하고 다음 명령이 성공하는지 확인합니다.

```bash
docker ps
```

### Pod가 `Pending`이고 `Insufficient memory`가 표시됨

```bash
kubectl -n qwen-serving describe pod -l serving.kserve.io/inferenceservice=qwen-mlx
```

Docker Desktop 메모리를 늘립니다. 로컬 values는 이미 동시에 Pod 두 개를 만들지 않는
`Recreate` 전략을 사용합니다.

### `ImagePullBackOff`

로컬 image를 Kind에 적재했는지 확인합니다.

```bash
task mlx-kind-image
```

`qwen-mlx-cpu:local` image를 다시 빌드한 뒤에는 `kind load docker-image`도 다시 해야 합니다.

### Pod가 오래 `0/1 Running` 상태임

모델 다운로드나 로딩 중일 수 있습니다.

```bash
kubectl -n qwen-serving logs -f deployment/qwen-mlx-predictor
kubectl -n qwen-serving describe pod -l serving.kserve.io/inferenceservice=qwen-mlx
```

### `localhost:8005`에 연결할 수 없음

포트포워딩 터미널이 실행 중인지 확인합니다.

```bash
task kserve-forward
```

Pod가 교체되면 기존 port-forward가 종료될 수 있으므로 다시 실행합니다.

### `8005 address already in use`

기존 `kubectl port-forward` 프로세스를 종료한 뒤 하나만 실행합니다.

### API는 연결되지만 답변이 매우 느림

Linux CPU에서 Qwen3-4B-4bit을 실행하는 현재 구조의 예상된 한계입니다. API와 배포 구조만
확인하려면 `/v1/models`를 사용하고, 답변 품질과 속도는 Mac 네이티브 MLX 또는 GPU 환경에서
검증합니다.

## 12. 종료와 초기화

전체 local cluster를 제거합니다.

```bash
task kind-down
```

이 명령은 Kind 노드 컨테이너와 내부 Pod, Service, 다운로드한 모델 cache를 함께 삭제합니다.
저장소의 코드와 Docker image는 삭제하지 않습니다.

cluster는 유지하고 모델 배포만 제거하려면 다음 명령을 사용할 수 있습니다.

```bash
helm uninstall qwen-mlx -n qwen-serving
```

## 13. 검증 방법

cluster를 만들지 않고 Helm 출력과 entrypoint revision 검증만 실행합니다.

```bash
task kserve-verify
```

전체 Python 테스트와 정적 검증은 다음 명령으로 실행합니다.

```bash
task verify
```

실제 cluster에서는 다음 세 조건을 별도로 확인합니다.

```bash
kubectl get nodes
kubectl -n qwen-serving get inferenceservice
kubectl -n qwen-serving get pods
```

## 14. 나중에 응용하는 방법

### 더 작은 로컬 모델로 빠르게 smoke하기

Helm values에서 MLX 호환 모델 ID와 고정 revision을 더 작은 모델로 바꾸면 같은 배포 구조를
유지하면서 추론 시간을 줄일 수 있습니다. 모델 변경 시 image를 다시 빌드할 필요는 없고
`task kserve-deploy`만 다시 실행하면 됩니다.

### 모델 cache 영속화

현재 `/models/cache`는 Pod와 함께 사라집니다. Pod 복구 시간을 비교하거나 반복 배포한다면
PVC를 생성해 이 경로에 mount할 수 있습니다.

```text
현재: Pod EmptyDir → Pod 삭제 시 모델 삭제
확장: PersistentVolumeClaim → 새 Pod가 기존 모델 재사용
```

로컬에서는 hostPath도 가능하지만 cloud 이전이 어려우므로 운영 구조에는 PVC 또는 KServe
LocalModel이 더 적합합니다.

### GPU cloud로 이전

Kind에서 학습한 KServe 구조는 유지하고 runtime image와 resources를 교체합니다.

```text
로컬
ServingRuntime → qwen-mlx-cpu:local
resources      → cpu, memory

GPU cloud
ServingRuntime → registry/vllm@sha256:... 또는 sglang@sha256:...
resources      → cpu, memory, nvidia.com/gpu: 1
```

GPU 환경에서는 다음 항목이 추가됩니다.

1. GPU node pool과 NVIDIA device plugin
2. vLLM 또는 SGLang image를 저장할 container registry
3. image tag 대신 검증한 digest
4. Hugging Face token과 engine API key를 위한 Secret
5. GPU node selector, toleration, resource limit
6. 같은 모델과 workload를 사용하는 benchmark

MLX CPU image를 GPU cloud에 그대로 사용하는 것이 아니라 `ServingRuntime`의 실행 engine을
vLLM 또는 SGLang으로 교체하는 방식입니다.

### port-forward를 외부 API로 교체

로컬에서는 port-forward가 가장 단순합니다. 외부 사용자가 접근해야 하면 다음 구조로
바뀝니다.

```text
로컬
Client → port-forward → ClusterIP Service

운영
Client → DNS/TLS → Gateway 또는 Ingress → KServe Service
```

공개 API에서는 모델 engine을 직접 노출하지 않고 Gateway에서 인증, rate limit, 요청 크기
제한과 공통 오류 형식을 적용합니다.

### Argo CD GitOps 추가

현재는 개발자가 직접 `helm upgrade`를 실행합니다. Argo CD를 추가하면 Git의 chart와 values가
배포의 기준이 됩니다.

```text
현재
개발자 → task kserve-deploy → Helm → Cluster

GitOps
CI가 image digest 검증
  → Git의 environment values 변경
  → Argo CD가 변경 감지
  → Helm chart 동기화
  → KServe가 Pod 갱신
```

이때 Secret 원문은 Git에 넣지 않고 External Secrets와 cloud secret manager를 사용합니다.

### replica와 autoscaling 추가

항상 요청이 있는 서비스는 replica를 2개 이상 유지하고 HPA나 KEDA로 확장할 수 있습니다.
트래픽이 오랫동안 없고 cold start를 허용할 수 있을 때만 Knative scale-to-zero를 검토합니다.

엔진 성능 비교 중에는 autoscaling을 끄고 replica 1개로 고정해야 Pod 수 변화가 TTFT와
throughput 측정에 섞이지 않습니다.

### 관측성 추가

운영 환경에서는 다음 두 계층을 함께 봐야 합니다.

```text
Kubernetes 계층
Pod restart, readiness, CPU/GPU memory, replica, scheduling

추론 계층
TTFT, TPOT, E2E p95, throughput, queue, token 수, 오류율
```

Prometheus가 metric을 수집하고 Grafana가 dashboard를 제공하도록 확장할 수 있습니다.

## 15. 추천 학습 순서

1. `task kind-up` 후 Docker 컨테이너와 Kubernetes node의 관계를 확인합니다.
2. `task kserve-install` 후 CRD와 KServe Controller를 확인합니다.
3. Helm template에서 `ServingRuntime`과 `InferenceService`의 차이를 읽습니다.
4. `task kserve-deploy` 전후의 Deployment와 Pod를 비교합니다.
5. Pod를 직접 삭제해 자동 복구를 확인합니다.
6. port-forward를 통해 Service와 Pod port의 차이를 확인합니다.
7. values의 CPU나 model revision을 바꾸고 재배포 흐름을 관찰합니다.
8. 같은 구조를 GPU vLLM·SGLang values로 확장합니다.

## 16. 핵심 질문과 답변

### Q. 모델은 어디에서 실행되는가?

Kind의 Kubernetes node 컨테이너 안에 생성된 `qwen-mlx-predictor` Pod에서 실행됩니다.

### Q. KServe가 모델을 실행하는가?

아닙니다. KServe는 Deployment와 Service를 관리하고, 실제 모델 실행은 MLX-LM이 담당합니다.

### Q. 왜 Service가 필요한가?

Pod 이름과 IP가 바뀌어도 고정된 주소로 Ready Pod에 요청을 전달하기 위해서입니다.

### Q. Gateway가 반드시 필요한가?

아닙니다. `localhost:8005`로 직접 요청하면 Gateway를 우회합니다. Chat UI나 외부 공개 API의
인증과 요청 통제가 필요할 때 Gateway를 사용합니다.

### Q. 왜 로컬 MLX-LM보다 느린가?

네이티브 MLX-LM은 Apple Silicon GPU와 unified memory를 사용하지만 Kind의 Linux CPU image는
CPU만 사용합니다. 현재 경로는 성능이 아니라 Kubernetes 동작 검증용입니다.

### Q. cloud에서도 Kind를 사용하는가?

아닙니다. Kind는 로컬 학습용입니다. cloud에서는 관리형 Kubernetes cluster의 GPU node에
같은 Helm/KServe 개념을 적용합니다.

### Q. 현재 구현에서 다음으로 할 일은 무엇인가?

GPU cluster에서 vLLM과 SGLang용 `ServingRuntime`과 values를 만들고, 동일한 모델·GPU·workload로
성능을 비교한 뒤 Argo CD와 관측성을 연결하는 것입니다.

## 참고 자료

- [GKE Standard와 Autopilot 선택](https://docs.cloud.google.com/kubernetes-engine/docs/concepts/choose-cluster-mode)
- [GKE GPU 구성](https://docs.cloud.google.com/kubernetes-engine/docs/concepts/gpus)
- [Helm template과 values](https://docs.helm.sh/docs/chart_template_guide/getting_started/)
- [Argo CD](https://argo-cd.readthedocs.io/)
- [KServe](https://kserve.github.io/website/)
