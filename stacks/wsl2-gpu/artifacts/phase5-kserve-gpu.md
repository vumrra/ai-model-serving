# Phase 5 — KServe GPU

Status: **PASS** — 2026-08-21 KST

| Item | Result |
|---|---|
| KServe | v0.19.0, Standard Mode, `Ready=True` |
| Runtime | vLLM v0.8.5, pinned digest `6cf9808c...33d33` |
| Model | Qwen3-1.7B FP16, revision `70d244cc...1ad5e` |
| Limits | 1024 tokens, 1 sequence, GPU utilization 0.85 |
| Pod startup | 7m 21s including initial model download |
| Download / weight load / engine init | 249.38s / 59.23s / 73.93s |
| Peak observed VRAM | 5857 / 6144 MiB |
| Peak observed Minikube RAM | 7.61 / 8 GiB |
| Model cache PVC | Bound, 16 GiB; 7.1 GiB used after validation |
| `/v1/models` | 200, model `qwen3-1.7b`, 0.605s |
| Warm JSON chat | 200, 0.711s, `reasoning_content=null` |
| Warm SSE | 200, 51 tokens, TTFT 383ms, 11.9 tokens/s |
| Exposure | no Ingress; port-forward bound to `127.0.0.1:8005` |

The first weight download failed with a Hugging Face Xet `UnexpectedEof`. The PVC retained the partial cache; setting `HF_HUB_DISABLE_XET=1` switched to the regular HTTP path and completed without changing the model or quantization. The WSL2 DXCore library is mounted read-only; no Linux NVIDIA driver was installed.
