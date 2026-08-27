import asyncio
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from fastapi.responses import StreamingResponse

from benchmarks.runner import (
    GpuSample,
    NvidiaSmiSampler,
    RequestCase,
    collect_environment,
    expand_cases,
    load_workload,
    run_case,
)


def test_gpu_smoke_covers_json_and_sse(monkeypatch: pytest.MonkeyPatch) -> None:
    workload = load_workload(Path("benchmarks/workloads/smoke.yaml"), "Qwen/Qwen3-4B")
    cases = expand_cases(workload)
    monkeypatch.setenv("RUN_IMAGE_DIGEST", "ghcr.io/acme/qwen-vllm@sha256:" + "a" * 64)

    assert [case.payload["stream"] for case in cases] == [False, True]
    assert all(case.payload["model"] == "Qwen/Qwen3-4B" for case in cases)
    environment = collect_environment([])
    assert environment["run_image_digest"].endswith("a" * 64)
    assert "hostname" not in environment
    assert all("GPU-" not in item for item in environment.get("gpu") or [])


@pytest.mark.asyncio
async def test_runner_records_ttft_from_sse_content() -> None:
    app = FastAPI()

    @app.post("/v1/chat/completions")
    async def completion() -> StreamingResponse:
        async def events():
            yield 'data: {"choices":[{"delta":{"role":"assistant"}}]}\n\n'
            await asyncio.sleep(0)
            yield 'data: {"choices":[{"delta":{"content":"ok"}}]}\n\n'
            yield "data: [DONE]\n\n"

        return StreamingResponse(events(), media_type="text/event-stream")

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        result = await run_case(
            client,
            "http://test/v1/chat/completions",
            RequestCase(
                prompt_id="smoke:r1",
                payload={
                    "model": "Qwen/test",
                    "messages": [{"role": "user", "content": "secret prompt"}],
                    "stream": True,
                },
            ),
            {"Content-Type": "application/json"},
        )

    assert result.success is True
    assert result.status_code == 200
    assert result.ttft_ms is not None
    assert result.e2e_ms >= result.ttft_ms
    assert "secret prompt" not in str(result)


@pytest.mark.asyncio
async def test_runner_rejects_truncated_sse() -> None:
    app = FastAPI()

    @app.post("/v1/chat/completions")
    async def completion() -> StreamingResponse:
        async def events():
            yield 'data: {"choices":[{"delta":{"content":"partial"}}]}\n\n'

        return StreamingResponse(events(), media_type="text/event-stream")

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        result = await run_case(
            client,
            "http://test/v1/chat/completions",
            RequestCase(
                prompt_id="truncated:r1",
                payload={"model": "Qwen/test", "messages": [], "stream": True},
            ),
            {"Content-Type": "application/json"},
        )

    assert result.success is False
    assert result.error == "truncated_stream"


def test_gpu_sampler_summary() -> None:
    sampler = NvidiaSmiSampler()
    sampler.samples = [
        GpuSample(power_w=40.0, memory_used_mib=5000.0, utilization_pct=80.0),
        GpuSample(power_w=50.0, memory_used_mib=5500.0, utilization_pct=100.0),
    ]

    assert sampler.summary() == {
        "gpu_samples": 2,
        "gpu_power_w_mean": 45.0,
        "gpu_memory_used_mib_peak": 5500.0,
        "gpu_utilization_pct_mean": 90.0,
    }
