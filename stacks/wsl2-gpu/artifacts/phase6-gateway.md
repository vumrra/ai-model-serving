# Phase 6 — API Gateway

Status: **PASS** — 2026-08-21 KST

| Item | Result |
|---|---|
| Path | Client → FastAPI Gateway → KServe Service → vLLM → Qwen3-1.7B |
| Gateway image | linux/amd64, local ID `sha256:5d366ee0...bc263`, 156 MB |
| Pod | 1/1 Ready, 0 restarts, 53.49 MiB |
| API key | Kubernetes Secret; unauthenticated request returned 401 |
| Model mapping | `qwen-demo` → `qwen3-1.7b`; response rewritten to `qwen-demo` |
| Thinking | disabled; `reasoning_content=null`, no `<think>` output |
| Warm JSON | 200, 2.78s, `GATEWAY OK` |
| Warm SSE | 200, true content TTFT 448ms, total 2.13s |
| Validation | wrong model 404; 513 completion tokens 422 |
| Rate limit | 30 requests / 60s; 429 with `Retry-After` |
| Operations | `/livez`, `/readyz`, `/metrics`, `/version` verified |
| Exposure | ClusterIP only; port-forward bound to `127.0.0.1:8080` |
| UI | disabled; `/` returned 404; no Ingress created |

The local gate uses a Git-SHA tag because GHCR is not involved yet; the running image ID is recorded above. Phase 7 replaces the tag with the GHCR manifest digest. The API key is never stored in Git.
