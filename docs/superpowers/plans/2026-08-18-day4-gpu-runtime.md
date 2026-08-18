# Day 4 GPU Runtime Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build immutable vLLM/SGLang images and validate either image on one RunPod L40S with authenticated JSON and SSE smoke requests, without provisioning an instance during local development.

**Architecture:** Keep three workflows: normal CI, one manually dispatched GPU runtime workflow, and scheduled RunPod cleanup. Reuse the existing engine Dockerfiles, RunPod lifecycle scripts, benchmark runner, and smoke workload; add only the validation and orchestration needed to connect them safely.

**Tech Stack:** GitHub Actions, Docker Buildx, GHCR, Python 3.11, pytest, RunPod REST API, vLLM, SGLang

**Spec:** `docs/superpowers/specs/2026-08-18-day4-gpu-runtime-design.md`

## Global Constraints

- Do not create a RunPod instance while implementing or locally verifying this plan.
- Use `Qwen/Qwen3-4B` revision `1cfa9a7208912126459214e8b04321603b3df60c` with BF16, context length 8192, tensor parallel 1, and GPU memory utilization 0.90.
- Run only one engine per workflow dispatch and use one NVIDIA L40S.
- Pass runtime images to RunPod by immutable `@sha256:<64 lowercase hex>` digest.
- Never write API-key values to images, Pod summaries, logs, or artifacts.
- Preserve unrelated working-tree changes in `README.md`, `apps/gateway/main.py`, `scripts/run_local_engine.py`, `docs/model-and-inference-options.md`, and `.idea/`.

---

### Task 1: Harden RunPod creation and readiness boundaries

**Files:**
- Modify: `deploy/runpod/create_pod.py`
- Modify: `deploy/runpod/wait_ready.py`
- Test: `tests/unit/test_runpod_payload.py`
- Create: `tests/unit/test_runpod_readiness.py`

**Interfaces:**
- Consumes: common runtime environment variables from `engines/*/launch.yaml`
- Produces: `validate_runtime_image(image: str) -> None`, `wait_until_ready(url: str, api_key: str, timeout_seconds: int, poll_seconds: float = 10) -> None`

- [ ] **Step 1: Write failing payload validation tests**

Add literal cases proving that a tag-only image and malformed digest are rejected before a client can create a Pod, while `ghcr.io/acme/qwen-vllm@sha256:` plus 64 lowercase hex characters is accepted. Extend the existing payload assertion with `gpuTypeIds == ["NVIDIA L40S"]`, `gpuCount == 1`, and all six shared model settings.

- [ ] **Step 2: Run the payload tests and verify RED**

Run: `uv run pytest tests/unit/test_runpod_payload.py -q`

Expected: FAIL because `build_payload` currently accepts tag-only and malformed image names.

- [ ] **Step 3: Implement immutable-image validation**

Add one compiled regex and `validate_runtime_image`. Call it at the start of `build_payload`; keep the existing payload shape and secret reference behavior unchanged.

- [ ] **Step 4: Run the payload tests and verify GREEN**

Run: `uv run pytest tests/unit/test_runpod_payload.py -q`

Expected: PASS.

- [ ] **Step 5: Write failing readiness behavior tests**

Use a local `ThreadingHTTPServer` fixture, not a mocked `urlopen`, to prove that readiness retries a temporary 503 then accepts 200 with the bearer header, and raises `TimeoutError` when the endpoint never becomes ready.

- [ ] **Step 6: Run readiness tests and verify RED**

Run: `uv run pytest tests/unit/test_runpod_readiness.py -q`

Expected: FAIL because polling exists only inside the CLI `main` function.

- [ ] **Step 7: Extract and implement the readiness function**

Move the polling loop into `wait_until_ready`; keep `main` responsible only for argument/file parsing. Validate positive timeout and poll intervals so local tests can use a short poll.

- [ ] **Step 8: Run Task 1 tests**

Run: `uv run pytest tests/unit/test_runpod_payload.py tests/unit/test_runpod_readiness.py -q`

Expected: PASS.

### Task 2: Make the GPU smoke result self-identifying

**Files:**
- Modify: `benchmarks/runner.py`
- Modify: `benchmarks/workloads/smoke.yaml`
- Test: `tests/load/test_benchmark_runner.py`

**Interfaces:**
- Consumes: OpenAI-compatible `/v1/chat/completions`, `RUN_IMAGE_DIGEST`, and workflow labels
- Produces: one benchmark JSON containing engine, model revision, immutable image digest, GPU metadata, and successful JSON/SSE request results

- [ ] **Step 1: Write a failing smoke-workload coverage test**

Load the real `benchmarks/workloads/smoke.yaml`, expand its cases, and assert that it contains exactly one non-streaming request and one streaming request. Keep the existing real in-process FastAPI tests for successful SSE and missing `[DONE]`. Add a `collect_environment` assertion that a literal immutable `RUN_IMAGE_DIGEST` is preserved.

- [ ] **Step 2: Run the runner tests and verify RED**

Run: `uv run pytest tests/load/test_benchmark_runner.py -q`

Expected: FAIL because the current smoke workload contains only streaming coverage.

- [ ] **Step 3: Add one JSON and one SSE smoke case**

Keep concurrency 1, rounds 1, temperature 0, top_p 1, thinking off, and max_tokens 16. Use short non-secret prompts and separate prompt IDs so the artifact proves both response modes.

- [ ] **Step 4: Implement only runner changes required by the failing behavior test**

Preserve sanitized errors and prompt-free result output. Do not add a second smoke client.

- [ ] **Step 5: Run Task 2 tests**

Run: `uv run pytest tests/load/test_benchmark_runner.py tests/load/test_benchmark_summary.py -q`

Expected: PASS.

### Task 3: Consolidate GitHub Actions around the current day

**Files:**
- Create: `.github/workflows/gpu-runtime.yaml`
- Delete: `.github/workflows/build-images.yaml`
- Delete: `.github/workflows/benchmark-gpu.yaml`
- Delete: `.github/workflows/deploy-staging.yaml`
- Delete: `.github/workflows/promote-demo.yaml`
- Delete: `.github/workflows/rollback.yaml`
- Modify: `.github/workflows/cleanup-runpod.yaml`
- Create: `scripts/verify_gpu_workflow.py`
- Create: `tests/unit/test_gpu_workflow.py`

**Interfaces:**
- Consumes: workflow input `engine`, engine-specific base-image reference, `RUNPOD_API_KEY`, `RUNPOD_REGISTRY_AUTH_ID`, `RUNPOD_ENGINE_SECRET_NAME`, and `ENGINE_API_KEY`
- Produces: `ghcr.io/<owner>/qwen-<engine>@sha256:<digest>` and artifact `gpu-smoke-<engine>-<run-id>`

- [ ] **Step 1: Write failing semantic workflow tests**

Parse workflow YAML and call `scripts.verify_gpu_workflow.verify`. Assert the workflow accepts exactly `vllm` and `sglang`, selects the matching Dockerfile and image repository, passes the built digest to `create_pod.py`, runs the smoke workload, uploads results, and has an `always()` Pod deletion step. Assert only `ci.yaml`, `gpu-runtime.yaml`, and `cleanup-runpod.yaml` remain.

- [ ] **Step 2: Run workflow tests and verify RED**

Run: `uv run pytest tests/unit/test_gpu_workflow.py -q`

Expected: FAIL because `gpu-runtime.yaml` and the verifier do not exist.

- [ ] **Step 3: Implement the workflow verifier**

Load YAML with `yaml.safe_load`, validate behavior-bearing fields, and exit nonzero with concise errors. Avoid exact whole-file text comparisons.

- [ ] **Step 4: Create the consolidated workflow**

Use manual `engine`, `base_image`, and `engine_version` inputs. A metadata step maps the fixed engine choice to its Dockerfile and `qwen-vllm` or `qwen-sglang` repository. Build/push one engine image, export the digest, create one L40S Pod, wait for readiness, run `benchmarks.runner` with `smoke.yaml`, upload `pod.json` and smoke JSON, and delete the Pod under `if: always()`. Do not build the Gateway or create a release manifest on day 4.

- [ ] **Step 5: Remove speculative future workflows**

Delete staging, promotion, rollback, and the two replaced GPU workflows. Keep scheduled cleanup as the cancellation safety net and align its environment names with `gpu-runtime.yaml`.

- [ ] **Step 6: Run Task 3 tests and verifier**

Run: `uv run pytest tests/unit/test_gpu_workflow.py -q`

Run: `uv run python scripts/verify_gpu_workflow.py`

Expected: both PASS.

### Task 4: Document and expose the day-4 developer flow

**Files:**
- Modify: `README.md`
- Modify: `docs/cicd-setup.md`
- Modify: `Taskfile.yml`

**Interfaces:**
- Consumes: the consolidated workflow and existing launch manifests
- Produces: `task gpu-verify` for local static checks and exact GitHub environment setup instructions

- [ ] **Step 1: Add the local verification command**

Add `gpu-verify` that runs `scripts/verify_gpu_workflow.py` and the focused RunPod/workflow/benchmark tests. The default command must not call RunPod or pull multi-gigabyte GPU images.

- [ ] **Step 2: Update documentation**

Mark day 4 as locally implemented with remote L40S smoke pending. Document why only three workflows remain, the `engine` dispatch input, required GitHub secrets/variables, one-engine-at-a-time cost behavior, expected artifacts, and the exact boundary between day 4 and days 5–9.

- [ ] **Step 3: Run documentation/config checks**

Run: `git diff --check`

Run: `uv run python scripts/verify_gpu_workflow.py`

Expected: all exit 0.

### Task 5: Full verification

**Files:**
- Modify only files required to fix failures caused by Tasks 1–4

**Interfaces:**
- Consumes: all day-4 changes
- Produces: a locally verified implementation that performs no cloud mutation

- [ ] **Step 1: Run focused tests**

Run: `uv run pytest tests/unit/test_runpod_payload.py tests/unit/test_runpod_readiness.py tests/unit/test_gpu_workflow.py tests/load/test_benchmark_runner.py tests/load/test_benchmark_summary.py -q`

Expected: PASS.

- [ ] **Step 2: Run repository verification**

Run: `uv run ruff check .`

Run: `uv run ruff format --check .`

Run: `uv run pyright`

Run: `uv run pytest -q`

Expected: all exit 0.

- [ ] **Step 3: Inspect the final diff**

Run: `git status --short`

Run: `git diff --check`

Confirm no RunPod API call was made, no secret value is present, and unrelated user changes remain untouched.
