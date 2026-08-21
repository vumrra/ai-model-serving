# 6단계 — API 게이트웨이

상태: **통과** — 2026-08-21 KST

| 항목 | 결과 |
|---|---|
| 경로 | 클라이언트 → FastAPI 게이트웨이 → KServe 서비스 → vLLM → Qwen3-1.7B |
| 게이트웨이 이미지 | linux/amd64, 로컬 ID `sha256:5d366ee0...bc263`, 156 MB |
| Pod | 1/1 준비 완료, 재시작 0회, 53.49 MiB |
| API 키 | Kubernetes Secret, 미인증 요청은 401 반환 |
| 모델 매핑 | `qwen-demo` → `qwen3-1.7b`, 응답은 `qwen-demo`로 변환 |
| Thinking | 비활성, `reasoning_content=null`, `<think>` 출력 없음 |
| 웜 JSON | 200, 2.78초, `GATEWAY OK` |
| 웜 SSE | 200, 실제 콘텐츠 TTFT 448ms, 전체 2.13초 |
| 검증 | 잘못된 모델 404, 완료 토큰 513개 요청 422 |
| 요청 제한 | 60초당 30회, 초과 시 `Retry-After`와 429 반환 |
| 운영 엔드포인트 | `/livez`, `/readyz`, `/metrics`, `/version` 검증 |
| 노출 범위 | ClusterIP 전용, 포트 포워딩은 `127.0.0.1:8080`에만 바인딩 |
| UI | 비활성, `/`는 404 반환, Ingress 없음 |

로컬 단계에서는 아직 GHCR을 사용하지 않으므로 Git SHA 태그를 사용했고 실행 이미지 ID를 위에 기록했다. 7단계에서 이 태그를 GHCR 매니페스트 다이제스트로 교체했다. API 키는 Git에 저장하지 않는다.
