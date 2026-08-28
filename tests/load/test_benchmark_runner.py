import asyncio
import json
import threading
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

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
    main,
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
            memory_free_mib=1144.0,
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
            memory_free_mib=644.0,
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
    assert summary["gpu_memory_free_mib_min"] == 644.0
    assert summary["gpu_utilization_pct_mean"] == 90.0
    sampler.clear()
    assert sampler.summary()["gpu_samples"] == 0
    assert summary["gpu_temperature_c_peak"] == 60.0
    assert summary["gpu_graphics_clock_mhz_mean"] == 1650.0
    assert summary["gpu_sm_clock_mhz_peak"] == 1750.0
    assert summary["system_memory_used_mib_peak"] == 7000.0
    assert summary["system_swap_used_mib_p95"] == pytest.approx(486.4)


def test_gpu_sampler_clear_waits_for_inflight_read_before_erasing_sample(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entered_readline = threading.Event()
    release_readline = threading.Event()
    clear_finished = threading.Event()

    class BlockingOutput:
        emitted = False

        def readline(self) -> str:
            if self.emitted:
                return ""
            self.emitted = True
            entered_readline.set()
            assert release_readline.wait(timeout=1)
            return "40, 5000, 1000, 80, 50, 1500, 1450\n"

    sampler = NvidiaSmiSampler()
    sampler._process = cast(Any, SimpleNamespace(stdout=BlockingOutput()))
    monkeypatch.setattr("benchmarks.runner.read_system_memory", lambda: (6000.0, 0.0))

    collector = threading.Thread(target=sampler._collect)
    collector.start()
    assert entered_readline.wait(timeout=1)

    clearer = threading.Thread(target=lambda: (sampler.clear(), clear_finished.set()))
    clearer.start()
    assert not clear_finished.wait(timeout=0.05)

    release_readline.set()
    collector.join(timeout=1)
    clearer.join(timeout=1)

    assert not collector.is_alive()
    assert clear_finished.is_set()
    assert sampler.samples == []


def test_read_system_memory_uses_available_and_free_swap(tmp_path: Path) -> None:
    meminfo = tmp_path / "meminfo"
    meminfo.write_text(
        "MemTotal: 10240 kB\nMemAvailable: 4096 kB\nSwapTotal: 2048 kB\nSwapFree: 512 kB\n",
        encoding="utf-8",
    )

    assert read_system_memory(meminfo) == (6.0, 1.5)


@pytest.mark.asyncio
async def test_execute_starts_sampler_before_warmup_and_clears_samples(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    sampler = NvidiaSmiSampler()

    def sample(power_w: float) -> GpuSample:
        return GpuSample(power_w, 0.0, 0.0)

    sampler.samples.append(sample(0.0))
    monkeypatch.setattr(sampler, "start", lambda: events.append("start"))
    monkeypatch.setattr(sampler, "stop", lambda: events.append("stop"))
    request_count = 0

    async def successful_case(*args: object, **kwargs: object) -> RequestResult:
        nonlocal request_count
        request_count += 1
        phase = "warmup" if request_count == 1 else "measurement"
        events.append(phase)
        sampler.samples.append(sample(float(request_count)))
        return RequestResult("id", phase, True, 200, None, 1.0)

    clock = iter((10.0, 11.5))

    def perf_counter() -> float:
        events.append(f"timer:{len(sampler.samples)}")
        return next(clock)

    monkeypatch.setattr("benchmarks.runner.run_case", successful_case)
    monkeypatch.setattr("benchmarks.runner.time.perf_counter", perf_counter)
    workload = {
        "execution": {"warmup_requests": 1},
        "prompts": [{"id": "case", "messages": []}],
    }

    results, duration = await execute(
        endpoint="http://unused",
        workload=workload,
        api_key=None,
        gpu_sampler=sampler,
    )

    assert len(results) == 1
    assert duration == 1.5

    assert events == ["start", "warmup", "timer:0", "measurement", "timer:1", "stop"]
    assert [item.power_w for item in sampler.samples] == [2.0]


@pytest.mark.asyncio
async def test_execute_aborts_when_warmup_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    events: list[str] = []
    sampler = NvidiaSmiSampler()
    monkeypatch.setattr(sampler, "start", lambda: events.append("start"))
    monkeypatch.setattr(sampler, "stop", lambda: events.append("stop"))

    async def failed_warmup(*args: object, **kwargs: object) -> RequestResult:
        events.append("warmup")
        return RequestResult("id", "warmup", False, 500, None, 1.0, error="http_500")

    monkeypatch.setattr("benchmarks.runner.run_case", failed_warmup)
    workload = {
        "execution": {"warmup_requests": 1},
        "prompts": [{"id": "case", "messages": []}],
    }

    with pytest.raises(RuntimeError, match="warmup_failed"):
        await execute(
            endpoint="http://unused",
            workload=workload,
            api_key=None,
            gpu_sampler=sampler,
        )
    assert events == ["start", "warmup", "stop"]


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
    assert args.disable_gpu_sampler is False
    disabled = build_parser().parse_args([*required, "--disable-gpu-sampler"])
    assert disabled.disable_gpu_sampler is True

    with pytest.raises(SystemExit):
        build_parser().parse_args([*required, "--concurrency", "0"])


def test_main_records_enabled_gpu_sampler_mode(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    output = tmp_path / "result.json"

    async def fake_execute(**kwargs: object) -> tuple[list[RequestResult], float]:
        assert isinstance(kwargs["gpu_sampler"], NvidiaSmiSampler)
        return [RequestResult("request", "prompt", True, 200, 1.0, 2.0)], 0.25

    monkeypatch.setattr("benchmarks.runner.execute", fake_execute)
    monkeypatch.setattr("benchmarks.runner.collect_environment", lambda _labels: {})

    exit_code = main(
        [
            "--endpoint",
            "http://test/v1/chat/completions",
            "--workload",
            "benchmarks/workloads/smoke.yaml",
            "--engine",
            "test",
            "--model",
            "Qwen/test",
            "--model-revision",
            "revision",
            "--output",
            str(output),
        ]
    )
    environment = json.loads(output.read_text(encoding="utf-8"))["environment"]

    assert exit_code == 0
    assert environment["gpu_sampler"] == "started-before-warmup-cleared-before-measurement"


def test_main_disables_gpu_sampler(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    output = tmp_path / "result.json"

    async def fake_execute(**kwargs: object) -> tuple[list[RequestResult], float]:
        assert kwargs["gpu_sampler"] is None
        return [RequestResult("request", "prompt", True, 200, 1.0, 2.0)], 0.25

    monkeypatch.setattr("benchmarks.runner.execute", fake_execute)
    monkeypatch.setattr("benchmarks.runner.collect_environment", lambda _labels: {})

    exit_code = main(
        [
            "--endpoint",
            "http://test/v1/chat/completions",
            "--workload",
            "benchmarks/workloads/smoke.yaml",
            "--engine",
            "test",
            "--model",
            "Qwen/test",
            "--model-revision",
            "revision",
            "--output",
            str(output),
            "--disable-gpu-sampler",
        ]
    )
    environment = json.loads(output.read_text(encoding="utf-8"))["environment"]

    assert exit_code == 0
    assert environment["gpu_sampler"] == "disabled"
    assert "gpu_samples" not in environment
