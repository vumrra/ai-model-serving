# WSL2 GPU 서빙

Qwen3-1.7B FP16을 WSL2의 Minikube/KServe에서 API로 서빙한다.

```text
Client -> FastAPI Gateway -> KServe Service -> vLLM -> Qwen3-1.7B
```

## 고정 사양

- GPU: GTX 1660 6GB, `nvidia.com/gpu: 1`
- vLLM: `v0.8.5@sha256:6cf9808c...a33d33`
- 모델 리비전: `70d244cc...b1ad5e`
- FP16, 컨텍스트 1024, 시퀀스 1, GPU 메모리 사용률 0.85
- WSL2 NVML/DXCore는 디바이스 플러그인과 GPU Pod에 읽기 전용 마운트
- Web UI, 양자화, CPU 오프로딩, Knative, Istio 없음

## 단계별 실행

```bash
task -d stacks/wsl2-gpu verify
task -d stacks/wsl2-gpu docker-gpu-smoke
task -d stacks/wsl2-gpu minikube-up
task -d stacks/wsl2-gpu minikube-gpu-smoke
task -d stacks/wsl2-gpu kserve-install
task -d stacks/wsl2-gpu kserve-deploy
task -d stacks/wsl2-gpu kserve-forward
task -d stacks/wsl2-gpu gateway-image-build
PUBLIC_API_KEY=change-me task -d stacks/wsl2-gpu gateway-deploy
task -d stacks/wsl2-gpu gateway-forward
task -d stacks/wsl2-gpu argocd-install
GIT_REVISION=main task -d stacks/wsl2-gpu argocd-bootstrap
```

각 단계가 통과한 뒤 다음 명령을 실행한다. Windows NVIDIA 드라이버만 사용하며 WSL에 Linux 드라이버를 설치하지 않는다.

`kserve-forward`와 `gateway-forward`는 각각 `127.0.0.1:8005`, `127.0.0.1:8080`에만 연다. API 키는 Git에 저장하지 않는다.

게이트웨이 이미지는 GitHub Actions가 GHCR 다이제스트로 고정한다. Argo CD는 Git을 가져오며 롤백은 Git revert로 수행한다.
