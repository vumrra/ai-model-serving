# WSL2 GPU serving

Qwen3-1.7B FP16을 WSL2의 Minikube/KServe에서 API로 서빙한다.

```text
Client -> FastAPI Gateway -> KServe Service -> vLLM -> Qwen3-1.7B
```

## 고정값

- GPU: GTX 1660 6GB, `nvidia.com/gpu: 1`
- vLLM: `v0.8.5@sha256:6cf9808c...a33d33`
- Model revision: `70d244cc...b1ad5e`
- FP16, context 1024, sequence 1, GPU utilization 0.85
- WSL2 NVML/DXCore는 device plugin과 GPU Pod에 read-only mount
- Web UI, quantization, CPU offload, Knative, Istio 없음

## Gate

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
```

각 gate가 통과한 뒤 다음 명령을 실행한다. Windows NVIDIA driver만 사용하며 WSL에 Linux driver를 설치하지 않는다.

`kserve-forward`와 `gateway-forward`는 각각 `127.0.0.1:8005`, `127.0.0.1:8080`에만 연다. API key는 Git에 저장하지 않는다.
