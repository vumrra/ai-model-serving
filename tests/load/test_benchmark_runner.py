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
    apply_execution_overrides,
    build_parser,
    collect_environment,
    execute,
    expand_cases,
    load_workload,
    read_system_memory,
    run_case,
    workload_metadata,
)
from benchmarks.schema import RequestResult


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
        GpuSample(
            power_w=40.0,
            memory_used_mib=5000.0,
            utilization_pct=80.0,
            temperature_c=50.0,
            graphics_clock_mhz=1500.0,
            sm_clock_mhz=1450.0,
            system_memory_used_mib=6000.0,
            system_swap_used_mib=0.0,
        ),
        GpuSample(
            power_w=50.0,
            memory_used_mib=5500.0,
            utilization_pct=100.0,
            temperature_c=60.0,
            graphics_clock_mhz=1800.0,
            sm_clock_mhz=1750.0,
            system_memory_used_mib=7000.0,
            system_swap_used_mib=512.0,
        ),
    ]

    summary = sampler.summary()

    assert summary["gpu_samples"] == 2
    assert summary["gpu_power_w_mean"] == 45.0
    assert summary["gpu_power_w_p95"] == 49.5
    assert summary["gpu_power_w_peak"] == 50.0
    assert summary["gpu_memory_used_mib_mean"] == 5250.0
    assert summary["gpu_memory_used_mib_p95"] == 5475.0
    assert summary["gpu_memory_used_mib_peak"] == 5500.0
    assert summary["gpu_utilization_pct_mean"] == 90.0
    assert summary["gpu_temperature_c_peak"] == 60.0
    assert summary["gpu_graphics_clock_mhz_mean"] == 1650.0
    assert summary["gpu_sm_clock_mhz_peak"] == 1750.0
    assert summary["system_memory_used_mib_peak"] == 7000.0
    assert summary["system_swap_used_mib_p95"] == pytest.approx(486.4)


def test_read_system_memory_uses_available_and_free_swap(tmp_path: Path) -> None:
    meminfo = tmp_path / "meminfo"
    meminfo.write_text(
        "MemTotal: 10240 kB\nMemAvailable: 4096 kB\nSwapTotal: 2048 kB\nSwapFree: 512 kB\n",
        encoding="utf-8",
    )

    assert read_system_memory(meminfo) == (6.0, 1.5)


@pytest.mark.asyncio
async def test_execute_aborts_when_warmup_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    async def failed_warmup(*args: object, **kwargs: object) -> RequestResult:
        return RequestResult("id", "warmup", False, 500, None, 1.0, error="http_500")

    monkeypatch.setattr("benchmarks.runner.run_case", failed_warmup)
    workload = {
        "execution": {"warmup_requests": 1},
        "prompts": [{"id": "case", "messages": []}],
    }

    with pytest.raises(RuntimeError, match="warmup_failed"):
        await execute(endpoint="http://unused", workload=workload, api_key=None)


def test_execution_overrides_and_canonical_metadata() -> None:
    workload = {
        "schema_version": 1,
        "name": "test",
        "defaults": {"model": "Qwen/test"},
        "execution": {"concurrency": 1, "rounds": 2},
        "prompts": [{"id": "a", "messages": []}],
    }
    apply_execution_overrides(workload, concurrency=4, rounds=3)
    reordered = {
        "prompts": workload["prompts"],
        "execution": {"rounds": 3, "concurrency": 4},
        "defaults": workload["defaults"],
        "name": "test",
        "schema_version": 1,
    }

    metadata = workload_metadata(workload)

    assert metadata == {
        "workload_sha256": workload_metadata(reordered)["workload_sha256"],
        "execution_concurrency": 4,
        "execution_rounds": 3,
    }


def test_cli_execution_overrides_must_be_positive() -> None:
    required = [
        "--endpoint",
        "http://test",
        "--workload",
        "workload.yaml",
        "--engine",
        "vllm",
        "--model-revision",
        "revision",
        "--output",
        "result.json",
    ]
    args = build_parser().parse_args([*required, "--concurrency", "2", "--rounds", "3"])
    assert (args.concurrency, args.rounds) == (2, 3)

    with pytest.raises(SystemExit):
        build_parser().parse_args([*required, "--concurrency", "0"])
