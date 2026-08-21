# Phase 7 — GitOps delivery

Status: **PASS** — 2026-08-21 KST

| Item | Result |
|---|---|
| GitHub Actions | Run `32475647318` succeeded: lint, tests, linux/amd64 build, GHCR push, GitOps commit |
| Gateway image | `ghcr.io/vumrra/ai-model-serving/gateway@sha256:b735e38e2548b9060030f2d88eaa1d90e813dae7954c2ddfd6731af77a7c94ce` |
| Validated workload revision | `b512c8da7d1887ab6aa38b04f32b2fb4695989c0` on `codex/windows-gpu` |
| Argo CD | root, cert-manager, KServe CRDs/controller, model, and Gateway all `Synced/Healthy` |
| PostSync | `qwen-gateway-smoke` succeeded, then removed by hook policy |
| Model API | `/v1/models` 200; `qwen-demo` alias returned |
| JSON chat | 200, `GITOPS OK`, `reasoning_content=null` |
| Warm JSON | 200, 0.615s for one generated token |
| Warm SSE | 200, TTFT 0.591s, total 1.263s, `reasoning_content=null` |
| GPU | GTX 1660, driver 560.94, 5,870 / 6,144 MiB during inference |
| Memory | model cgroup 4,643,954,688 bytes including file cache; Gateway 58,601,472 bytes; Minikube 4.69 / 8 GiB |
| Exposure | Gateway is ClusterIP and localhost port-forward only; Argo CD and vLLM are not public |

Bootstrap initially exposed two contract defects: `/` in the branch name broke the Task's `sed` expression, and cert-manager leader election needed the project to permit `kube-system`. KServe also defaults `model.name` and normalizes GPU quantities, so the WSL-only GitOps definition now accounts for both without changing the Apple CPU stack.
