# WSL2 GPU 서빙

Qwen3-1.7B FP16을 WSL2의 Minikube/KServe에서 API로 서빙한다.

```text
Client -> Windows TCP 8000 -> FastAPI Gateway -> KServe -> vLLM -> Qwen3-1.7B
```

## 고정 사양

- GPU: GTX 1660 6GB, `nvidia.com/gpu: 1`
- vLLM: `v0.8.5@sha256:6cf9808c...a33d33`
- 모델 리비전: `70d244cc...b1ad5e`
- FP16, 컨텍스트 1024, 시퀀스 1, GPU 메모리 사용률 0.85
- WSL2 메모리 10GB, swap 4GB, Minikube 메모리 8GB
- Web UI, 양자화, CPU 오프로딩, Knative, Istio 없음

## 최초 1회 설정

Windows NVIDIA 드라이버와 Docker Desktop만 설치한다. WSL 내부에 Linux NVIDIA 드라이버를 설치하지 않는다. Docker Desktop에서 Ubuntu WSL Integration을 활성화한다.

`%USERPROFILE%\.wslconfig`:

```ini
[wsl2]
memory=10GB
swap=4GB
localhostForwarding=true
```

PowerShell:

```powershell
wsl --update --web-download
wsl --set-default-version 2
wsl -d Ubuntu -- nvidia-smi
docker run --rm --gpus all ubuntu nvidia-smi
```

저장소는 `/mnt/c`가 아닌 WSL Linux 파일시스템에 받는다.

```bash
wsl -d Ubuntu
mkdir -p ~/Project
cd ~/Project
git clone https://github.com/vumrra/ai-model-serving.git qwen-serving-lab
cd qwen-serving-lab
git switch main
```

각 단계가 통과한 뒤 다음 단계로 진행한다.

```bash
task -d stacks/wsl2-gpu verify
task -d stacks/wsl2-gpu docker-gpu-smoke
task -d stacks/wsl2-gpu minikube-up
task -d stacks/wsl2-gpu minikube-gpu-smoke
task -d stacks/wsl2-gpu kserve-install
task -d stacks/wsl2-gpu kserve-deploy
task -d stacks/wsl2-gpu gateway-image-build
PUBLIC_API_KEY='change-me' task -d stacks/wsl2-gpu gateway-deploy
task -d stacks/wsl2-gpu argocd-install
GIT_REVISION=main task -d stacks/wsl2-gpu argocd-bootstrap
```

API 키는 Git에 저장하지 않는다. 클러스터를 삭제하지 않았다면 위 설치 명령은 재부팅할 때 다시 실행하지 않는다.

## 재부팅 후 시작

일반 PowerShell에서 다음 한 줄을 실행한다.

```powershell
wsl -d Ubuntu -- true; powershell.exe -NoProfile -ExecutionPolicy Bypass -File "\\wsl.localhost\Ubuntu\home\vumrra\Project\qwen-serving-lab\stacks\wsl2-gpu\scripts\start.ps1" -RecoverFailedGpuPod
```

재부팅 직후 NVIDIA plugin보다 GPU Pod가 먼저 복구되어 `UnexpectedAdmissionError`가 난 경우에는 실패한 Pod 하나만 재생성한다. 이 동작을 원하지 않으면 `-RecoverFailedGpuPod`를 빼고 실행한다.

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "\\wsl.localhost\Ubuntu\home\vumrra\Project\qwen-serving-lab\stacks\wsl2-gpu\scripts\start.ps1"
```

스크립트가 Docker Desktop을 시작하고 기존 `qwen-wsl2-gpu` Minikube 프로필과 모델을 복구한 뒤 게이트웨이를 Windows localhost `18000`에 연결한다. `-RecoverFailedGpuPod`는 실패한 모델 Pod만 삭제해 ReplicaSet이 다시 만들게 하며 PVC와 모델 캐시는 보존한다. 클러스터를 재설치하거나 Argo CD를 다시 bootstrap하지 않는다.

상태 확인:

```powershell
wsl -d Ubuntu -- kubectl get applications -n argocd
wsl -d Ubuntu -- kubectl get pods -n qwen-serving
curl.exe http://127.0.0.1:18000/readyz
```

GitHub Actions는 PC가 꺼져 있어도 GitHub에서 이미지 빌드와 GitOps 값 갱신을 완료한다. PC에서 Docker와 Minikube가 실행 중이면 Argo CD가 자동 동기화한다. PC가 꺼져 있었다면 위 시작 명령 실행 후 최신 Git 상태로 따라잡는다. PC 저장소에서 `git pull`할 필요는 없다.

## LAN API: TCP 8000

최초 1회 관리자 PowerShell에서 설치한다.

```powershell
wsl -d Ubuntu -- true
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "\\wsl.localhost\Ubuntu\home\vumrra\Project\qwen-serving-lab\stacks\wsl2-gpu\scripts\install-lan-port.ps1"
```

구성 경로:

```text
LAN client -> Windows :8000 -> Windows localhost :18000 -> qwen-gateway ClusterIP :80
```

- 방화벽은 `Private` 프로필의 `LocalSubnet`만 허용한다.
- Kubernetes API, Argo CD, Dashboard, vLLM 원본 API는 노출하지 않는다.
- HTTP이므로 신뢰할 수 있는 가정/사무실 LAN에서만 사용한다.
- 인터넷 접속에는 공유기 포트 포워딩 대신 Tailscale 또는 TLS 터널을 사용한다.

Windows LAN 주소 확인:

```powershell
Get-NetIPAddress -AddressFamily IPv4 | Where-Object IPAddress -NotLike '127.*'
```

API 주소는 `http://<WINDOWS_LAN_IP>:8000/v1`이다. 모든 요청에 기존 Gateway API 키가 필요하다.

## 수동 운영

```bash
task -d stacks/wsl2-gpu kserve-status
task -d stacks/wsl2-gpu gateway-status
task -d stacks/wsl2-gpu argocd-status
task -d stacks/wsl2-gpu kserve-forward   # localhost:8005, 진단 전용
task -d stacks/wsl2-gpu gateway-forward  # localhost:8080, 진단 전용
task -d stacks/wsl2-gpu argocd-forward   # localhost:8081, 진단 전용
```

게이트웨이 이미지는 GitHub Actions가 GHCR 다이제스트로 고정한다. Argo CD는 Git을 pull하며 롤백은 Git revert로 수행한다.
