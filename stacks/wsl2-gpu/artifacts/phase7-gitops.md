# 7단계 — GitOps 배포

상태: **통과** — 2026-08-21 KST

| 항목 | 결과 |
|---|---|
| GitHub Actions | 실행 `32475647318` 성공: 린트, 테스트, linux/amd64 빌드, GHCR 푸시, GitOps 커밋 |
| 게이트웨이 이미지 | `ghcr.io/vumrra/ai-model-serving/gateway@sha256:b735e38e2548b9060030f2d88eaa1d90e813dae7954c2ddfd6731af77a7c94ce` |
| 검증한 워크로드 리비전 | `codex/windows-gpu`의 `b512c8da7d1887ab6aa38b04f32b2fb4695989c0` |
| Argo CD | 루트, cert-manager, KServe CRD/컨트롤러, 모델, 게이트웨이 모두 `Synced/Healthy` |
| PostSync | `qwen-gateway-smoke` 성공 후 훅 정책에 따라 제거 |
| 모델 API | `/v1/models` 200, `qwen-demo` 별칭 반환 |
| JSON 채팅 | 200, `GITOPS OK`, `reasoning_content=null` |
| 웜 JSON | 생성 토큰 1개 기준 200, 0.615초 |
| 웜 SSE | 200, TTFT 0.591초, 전체 1.263초, `reasoning_content=null` |
| GPU | GTX 1660, 드라이버 560.94, 추론 중 5,870 / 6,144 MiB |
| 메모리 | 파일 캐시 포함 모델 cgroup 4,643,954,688바이트, 게이트웨이 58,601,472바이트, Minikube 4.69 / 8 GiB |
| 노출 범위 | 게이트웨이는 ClusterIP와 로컬 포트 포워딩만 사용, Argo CD와 vLLM은 외부 비공개 |

초기 부트스트랩에서 두 가지 계약 결함을 확인했다. 브랜치 이름의 `/`가 Task의 `sed` 표현식을 깨뜨렸고 cert-manager 리더 선출에는 프로젝트의 `kube-system` 허용이 필요했다. 또한 KServe가 `model.name` 기본값을 채우고 GPU 수량을 정규화하므로, Apple CPU 스택은 변경하지 않고 WSL 전용 GitOps 정의에서 두 차이를 처리했다.
