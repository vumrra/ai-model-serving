# 5단계 — KServe GPU

상태: **통과** — 2026-08-21 KST

| 항목 | 결과 |
|---|---|
| KServe | v0.19.0, Standard 모드, `Ready=True` |
| 런타임 | vLLM v0.8.5, 고정 다이제스트 `6cf9808c...33d33` |
| 모델 | Qwen3-1.7B FP16, 리비전 `70d244cc...1ad5e` |
| 제한 | 1024 토큰, 시퀀스 1개, GPU 메모리 사용률 0.85 |
| Pod 시작 | 최초 모델 다운로드 포함 7분 21초 |
| 다운로드 / 가중치 로드 / 엔진 초기화 | 249.38초 / 59.23초 / 73.93초 |
| 최대 관측 VRAM | 5857 / 6144 MiB |
| 최대 관측 Minikube RAM | 7.61 / 8 GiB |
| 모델 캐시 PVC | 연결 완료, 16 GiB 중 검증 후 7.1 GiB 사용 |
| `/v1/models` | 200, 모델 `qwen3-1.7b`, 0.605초 |
| 웜 JSON 채팅 | 200, 0.711초, `reasoning_content=null` |
| 웜 SSE | 200, 51토큰, TTFT 383ms, 11.9토큰/초 |
| 노출 범위 | Ingress 없음, 포트 포워딩은 `127.0.0.1:8005`에만 바인딩 |

첫 가중치 다운로드는 Hugging Face Xet의 `UnexpectedEof`로 실패했다. PVC가 일부 캐시를 보존했으며 `HF_HUB_DISABLE_XET=1`을 설정해 일반 HTTP 경로로 전환한 뒤 모델 변경이나 양자화 없이 완료했다. WSL2 DXCore 라이브러리는 읽기 전용으로 마운트했고 Linux NVIDIA 드라이버는 설치하지 않았다.
