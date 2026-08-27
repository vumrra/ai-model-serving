import pytest

from benchmarks.schema import BenchmarkRun, RequestResult
from benchmarks.summarize import percentile, summarize_run


def test_percentile_interpolates() -> None:
    assert percentile([10.0, 20.0, 30.0], 0.95) == 29.0
    assert percentile([], 0.95) is None


def test_summary_ignores_failed_latency() -> None:
    run = BenchmarkRun(
        schema_version=1,
        run_id="run-1",
        engine="fake",
        endpoint="http://example.test/v1/chat/completions",
        model="Qwen/test",
        model_revision="deadbeef",
        workload="smoke",
        started_at="2026-01-01T00:00:00+00:00",
        finished_at="2026-01-01T00:00:01+00:00",
        environment={"gpu": None},
        results=[
            RequestResult("1", "a", True, 200, 10.0, 50.0),
            RequestResult("2", "b", True, 200, 20.0, 70.0),
            RequestResult("3", "c", False, 500, None, 5.0, error="http_500"),
        ],
    )

    summary = summarize_run(run)

    assert summary["success_rate"] == 2 / 3
    assert summary["ttft_ms"]["p50"] == 15.0
    assert summary["e2e_ms"]["mean"] == 60.0


def test_summary_derives_tpot_throughput_slo_and_energy() -> None:
    run = BenchmarkRun(
        schema_version=1,
        run_id="run-2",
        engine="vllm",
        endpoint="http://example.test/v1/chat/completions",
        model="Qwen/test",
        model_revision="deadbeef",
        workload="chat",
        started_at="2026-01-01T00:00:00+00:00",
        finished_at="2026-01-01T00:00:01+00:00",
        environment={
            "benchmark_duration_seconds": 1,
            "gpu_samples": 2,
            "gpu_power_w_mean": 20,
            "gpu_memory_used_mib_peak": 5500,
            "gpu_utilization_pct_mean": 90,
            "electricity_krw_per_kwh": 200,
            "slo_ttft_p95_ms": 1000,
            "slo_tpot_p95_ms": 100,
        },
        results=[
            RequestResult("1", "a", True, 200, 10.0, 50.0, 8, 5),
            RequestResult("2", "b", True, 200, 20.0, 70.0, 9, 6),
        ],
    )

    summary = summarize_run(run)

    assert summary["tpot_ms"]["p95"] == 10.0
    assert summary["output_throughput_tokens_per_second"] == 11.0
    assert summary["output_tokens_per_hour"] == 39_600.0
    assert summary["goodput_requests_per_second"] == 2.0
    assert summary["slo"]["pass"] is True
    assert summary["energy"]["gpu_wh_per_1k_output_tokens"] == pytest.approx(0.5050505)
    assert summary["energy"]["estimated_gpu_cost_krw_per_million_output_tokens"] == pytest.approx(
        101.0101
    )
