# WSL2 GPU 서빙

Qwen3-1.7B FP16을 WSL2의 Minikube/KServe에서 API로 서빙한다.

```text
Client -> Windows TCP 8000 -> FastAPI Gateway -> KServe -> vLLM -> Qwen3-1.7B
```

## 최종 추천

| 목적 | 설정 | 실측 판단 |
| --- | --- | --- |
| 기본 API | Qwen3-1.7B FP16, `max-num-seqs=1` | TTFT p95 225.9ms, TPOT p95 92.7ms, 10.61 tok/s. 단일 GPU 대화형 기본값 |
| 두 사용자 처리량 | 같은 모델, `max-num-seqs=2` | aggregate 중앙 16.21 tok/s. TPOT p95 121.6ms로 100ms gate를 넘으므로 선택 프로파일 |
| 모델 용량 우선 | Qwen3-4B AWQ 실험 | 3-run 중앙 5.58 tok/s, TPOT p95 173.1ms. 대화형 TPOT 100ms gate는 실패했고, 원본 5,888MiB label은 legacy 계산 오류라 변조하지 않고, reserved 178MiB를 반영한 corrected used≤5,710MiB·free≥256MiB gate로 3/3 재계산 통과. 30-case 17/30으로 1.7B의 18/30보다 품질 우위는 확인되지 않음 |

기본 배포는 1.7B FP16/seq1이다. seq2는 동시에 두 요청을 처리해야 하고 느린 토큰 간격을 허용할 때만 사용한다. 4B AWQ는 더 큰 파라미터 수 자체가 필요한 경우의 실험 후보이며 기본 배포를 대체하지 않는다.

6GB 경계는 먼저 산술로 거른다. 4B FP16 ideal weights는 7,629MiB라 적재하지 않았다. 8B AWQ도 4B에서 관측한 non-weight envelope 약 3,429MiB와 ideal packed weights 약 3,815MiB를 합치면 반올림 전 기준 약 7,243MiB로 추론되어 기각했으며, 실제 load test는 실행하지 않았다.

서비스는 API only다. Open WebUI를 배포하지 않으며 외부에는 API key·rate limit·검증을 거치는 Gateway TCP 8000만 연다. Kubernetes API, Argo CD, Dashboard, vLLM 원본 API는 localhost에 남긴다.

## KServe 제어면 residual risk

이전 관측의 etcd `fdatasync` 최대는 3.891초였고, 최근 24시간 cluster live log에서는 최대 7.826초와 재시작 직전 7.517초를 확인했다. 약 3초 안에 manager와 storage-provisioner가 함께 종료됐다. 이 증거는 성능 study JSON이 아니라 live log의 시간 상관관계다. WSL 디스크 지연 → etcd commit stall → API timeout → lease 갱신 실패가 가장 일관된 해석이지만 단독 인과를 증명하지 않는다.

- read-only 확인에서 etcd dataDir은 `/var/lib/minikube/etcd`, Docker node의 `/var`는 `/dev/sdd`였다. 디렉터리 256MiB 중 WAL 245MiB, snapshot DB 12MiB였고 disk pressure는 false였다. 작은 DB와 pressure 부재는 용량 고갈·대형 DB 가설을 약화하고 storage path 지연 가설을 지지하지만 인과를 확정하지 않는다.
- controller CPU는 request 100m, limit 500m다. 500m limit은 burst 상한을 완화해 CPU throttling 가능성을 낮추려는 조치일 뿐, etcd persistence의 근본 해결이 아니며 사건 완화 효과도 검증되지 않았다.
- 잘못된 autoscaler class는 효과가 없어 HPA가 생성됐고 `autoscalerClass: none`으로 바로잡았다. 불필요한 HPA reconcile과 etcd write가 줄 수 있다는 것은 해석이며, 실제 감소량과 재시작 완화 효과는 측정하지 않았다.
- WSL 가상 디스크와 단일 노드 etcd가 남아 있으므로 controller 재시작 위험은 0이 아니다. 재발 시 restart 수만 보지 말고 fsync 지연, API timeout, lease-renew 실패의 시간 순서를 함께 본다.
- 다음 gate는 [etcd metrics](https://etcd.io/docs/v3.6/metrics/)의 `wal_fsync_duration_seconds` p99 계측과 [etcd tuning](https://etcd.io/docs/v3.7/tuning/)에 따른 SSD/저지연 storage A/B다.
- autoscaler 계약은 [KServe HPA Autoscaler 공식 문서](https://kserve.github.io/website/docs/model-serving/predictive-inference/autoscaling/hpa-autoscaler)를 기준으로 한다.

## 고정 사양

- GPU: GTX 1660 6GB, `nvidia.com/gpu: 1`
- vLLM: `v0.8.5@sha256:6cf9808c...a33d33`
- 모델 리비전: `70d244cc...b1ad5e`
- FP16, 컨텍스트 1024, 시퀀스 1, GPU 메모리 사용률 0.75, prefix caching 활성
- WSL2 메모리 10GB, swap 4GB, Minikube 메모리 8GB
- 기본 배포에는 Web UI, 양자화, CPU 오프로딩, Knative, Istio 없음. 4B AWQ는 용량 비교 실험에만 사용

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

스크립트가 Docker Desktop과 Ubuntu WSL Integration을 확인하고, 통합 시작이 실패하면 Docker Desktop을 한 번 재시작한다. 이후 기존 `qwen-wsl2-gpu` Minikube 프로필과 모델을 복구하고 게이트웨이를 Windows localhost `18000`에 연결한다. `-RecoverFailedGpuPod`는 실패한 모델 Pod만 삭제해 ReplicaSet이 다시 만들게 하며 PVC와 모델 캐시는 보존한다. 클러스터를 재설치하거나 Argo CD를 다시 bootstrap하지 않는다.

상태 확인:

```powershell
wsl -d Ubuntu -- kubectl get applications -n argocd
wsl -d Ubuntu -- kubectl get pods -n qwen-serving
curl.exe http://127.0.0.1:18000/readyz
```

GitHub Actions는 PC가 꺼져 있어도 GitHub에서 이미지 빌드와 GitOps 값 갱신을 완료한다. PC에서 Docker와 Minikube가 실행 중이면 Argo CD가 자동 동기화한다. PC가 꺼져 있었다면 위 시작 명령 실행 후 최신 Git 상태로 따라잡는다. PC 저장소에서 `git pull`할 필요는 없다.

### PR을 main에 merge한 뒤

WSL2 release workflow는 별도 repository Secret 없이 GitHub가 자동 발급하는 `GITHUB_TOKEN`으로 GHCR push와 GitOps commit을 수행한다. Gateway API 키는 GitHub Secret이 아니라 cluster의 `qwen-gateway-api-key` Secret으로 관리한다.

현재 개발 branch로 bootstrap한 cluster는 merge가 끝난 뒤 한 번만 `main`으로 인계한다.

```powershell
wsl -d Ubuntu -- bash -lc "cd ~/Project/qwen-serving-lab && GIT_REVISION=main task -d stacks/wsl2-gpu argocd-bootstrap"
wsl -d Ubuntu -- kubectl -n argocd get applications
```

이후에는 `main` push → GitHub Actions → GHCR digest/GitOps commit → Argo CD pull → Kubernetes sync가 자동으로 진행된다.

## LAN API: TCP 8000

최초 1회 관리자 PowerShell에서 설치한다.

```powershell
wsl -d Ubuntu -- true
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "\\wsl.localhost\Ubuntu\home\vumrra\Project\qwen-serving-lab\stacks\wsl2-gpu\scripts\install-lan-port.ps1"
```

방화벽은 `Private` 네트워크에서만 열린다. 현재 프로필을 확인하고, 신뢰하는 LAN인데 `Public`으로 표시될 때만 관리자 PowerShell에서 바꾼다.

```powershell
Get-NetConnectionProfile
Set-NetConnectionProfile -InterfaceIndex <INDEX> -NetworkCategory Private
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

## 성능 재현

첫 번째 WSL 터미널에서 진단용 vLLM 포트를 연 뒤 두 번째 터미널에서 최종 `0.75/prefix-on` 설정을 재현한다.

```bash
task -d stacks/wsl2-gpu kserve-forward

PERF_RUN_ID=run4 task -d stacks/wsl2-gpu perf-benchmark
task -d stacks/wsl2-gpu perf-soak
task -d stacks/wsl2-gpu perf-quality
task -d stacks/wsl2-gpu perf-startup
task -d stacks/wsl2-gpu perf-report
```

`PERF_RUN_ID`를 생략하면 benchmark는 `latest`에 저장된다. `perf-soak`은 최종 Qwen3-1.7B FP16 / util 0.75 / prefix-on 서비스에 약 33분간 부하를 발생시키며, 현재 endpoint에 실제 요청이 흐르는 점을 확인한 뒤 실행한다. 품질 점수가 만점이 아니어도 30개 결과와 Wilson 95% 신뢰구간을 저장하며, startup Task는 원본 Pod JSON을 남기지 않는다.

주요 artifact:

- 최종 1.7B 단기 3회: [run1](artifacts/performance/study/qwen3-1.7b-fp16-util075-short-c1-run1.json), [run2](artifacts/performance/study/qwen3-1.7b-fp16-util075-short-c1-run2.json), [run3](artifacts/performance/study/qwen3-1.7b-fp16-util075-short-c1-run3.json)
- seq1/seq2 C2: [seq1](artifacts/performance/study/qwen3-1.7b-fp16-util075-seq1-short-c2.json), [seq2 run1](artifacts/performance/study/qwen3-1.7b-fp16-util075-seq2-short-c2.json), [run2](artifacts/performance/study/qwen3-1.7b-fp16-util075-seq2-short-c2-run2.json), [run3](artifacts/performance/study/qwen3-1.7b-fp16-util075-seq2-short-c2-run3.json)
- 1.7B 품질·시작: [quality 30](artifacts/performance/study/qwen3-1.7b-fp16-quality-30.json), [warm startup](artifacts/performance/study/startup-qwen3-1.7b-util075-prefix-on.json)
- 4B AWQ 용량 실험: [run1](artifacts/performance/study/qwen3-4b-awq-util075-short-c1-run1.json), [run2](artifacts/performance/study/qwen3-4b-awq-util075-short-c1-run2.json), [run3](artifacts/performance/study/qwen3-4b-awq-util075-short-c1-run3.json), [quality 30](artifacts/performance/study/qwen3-4b-awq-util075-quality-30.json)
- 4B sampler lifecycle 대조: [sampler-primed 20](artifacts/performance/study/qwen3-4b-awq-util075-sampler-primed-20.json). 변경 조건에서도 결과가 일관됐지만 원인이나 해결로 확정하지 않는다.
- historical 30-case 품질 JSON은 case ID/order만 남아 revision·suite SHA·실행 시각·serving config를 artifact 단독으로 감사할 수 없다. 따라서 방향성 근거일 뿐 모델 선택의 단독 근거로 쓰지 않는다. 다음 재실행은 revision·config ID·suite SHA metadata를 함께 남긴다.
- 최종 1.7B soak·no-sampler 대조: [360-request soak](artifacts/performance/study/qwen3-1.7b-fp16-util075-final-soak-c1.json)는 360/360 성공, 32m41s measurement, aggregate SLO 통과·개별 358/360이다. [no-sampler 20](artifacts/performance/study/qwen3-1.7b-fp16-util075-no-sampler-20.json)은 20/20 성공했지만 작은 표본이므로 계측 인과를 확정하지 않는다. 별도 [control-plane 관찰 32m56s](artifacts/performance/study/kserve-control-plane-soak.md)도 함께 본다.
- 공유 prefix: [prefix-on 결과](artifacts/performance/study/qwen3-1.7b-fp16-util075-shared-prefix-on-c1.json)
- 상세 판단: [GTX 1660 LLM 서빙 실측 보고서](artifacts/performance/report.html)

artifact에는 요청별 latency·usage와 품질 규칙/hash만 저장하며 raw prompt·응답·API key는 저장하지 않는다.

## 관리 화면

두 명령은 각각 터미널을 점유하므로 일반 PowerShell 창을 따로 열어 실행한다. 둘 다 `127.0.0.1`에만 연결되며 LAN이나 인터넷에는 공개되지 않는다.

Kubernetes Dashboard:

```powershell
wsl -d Ubuntu -- bash -lc "cd ~/Project/qwen-serving-lab && task -d stacks/wsl2-gpu kubernetes-dashboard-forward"
```

- 접속: http://127.0.0.1:8001/api/v1/namespaces/kubernetes-dashboard/services/http:kubernetes-dashboard:/proxy/#/workloads?namespace=_all
- Minikube addon의 `Skip` 로그인을 사용한다.

Argo CD Dashboard:

```powershell
wsl -d Ubuntu -- bash -lc "cd ~/Project/qwen-serving-lab && task -d stacks/wsl2-gpu argocd-forward"
```

- 접속: http://127.0.0.1:8081
- 사용자명: `admin`
- 최초 비밀번호 확인:

```powershell
$encoded = wsl -d Ubuntu -- kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath='{.data.password}'
[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($encoded.Trim()))
```

포트포워드는 해당 PowerShell 창에서 `Ctrl+C`를 누르면 종료된다.

## 수동 운영

```bash
task -d stacks/wsl2-gpu kserve-status
task -d stacks/wsl2-gpu gateway-status
task -d stacks/wsl2-gpu argocd-status
task -d stacks/wsl2-gpu kserve-forward   # localhost:8005, 진단 전용
task -d stacks/wsl2-gpu gateway-forward  # localhost:8080, 진단 전용
task -d stacks/wsl2-gpu kubernetes-dashboard-forward # localhost:8001
task -d stacks/wsl2-gpu argocd-forward   # localhost:8081, 진단 전용
```

게이트웨이 이미지는 GitHub Actions가 GHCR 다이제스트로 고정한다. Argo CD는 Git을 pull하며 롤백은 Git revert로 수행한다.
