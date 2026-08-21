# 4단계 — Minikube GPU

상태: **통과** — 2026-08-21 KST

| 항목 | 결과 |
|---|---|
| Minikube | v1.38.1, Docker 드라이버/런타임 |
| Kubernetes | v1.35.1 |
| 노드 | 준비 완료, `nvidia.com/gpu: 1` |
| GPU Pod | 성공 |
| GPU | NVIDIA GeForce GTX 1660, 6144 MiB |
| 드라이버 / CUDA | 560.94 / 12.6 |
| 점검 이미지 | `ubuntu@sha256:2260313b...e09b` |
| Minikube 메모리 제한 | 8 GiB |

Docker Desktop의 WSL 통합은 Linux CLI와 소켓이 나타나기 전에 백엔드 전체 재시작이 필요했다. Minikube의 NVIDIA 플러그인은 WSL2 NVML과 DXCore 읽기 전용 마운트가 필요했으며 Linux NVIDIA 드라이버는 설치하지 않았다.
