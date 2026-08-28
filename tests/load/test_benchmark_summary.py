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
    assert summary["ttft_ms"]["stdev"] == 5.0
    assert summary["ttft_ms"]["min"] == 10.0
    assert summary["ttft_ms"]["max"] == 20.0
    assert summary["e2e_ms"]["mean"] == 60.0
    assert summary["slo"]["attainment_rate"] == 2 / 3


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
            "gpu_power_w_p95": 22,
            "gpu_power_w_peak": 25,
            "gpu_memory_used_mib_mean": 5000,
            "gpu_memory_used_mib_p95": 5400,
            "gpu_memory_used_mib_peak": 5500,
            "gpu_utilization_pct_mean": 90,
            "gpu_utilization_pct_p95": 98,
            "gpu_utilization_pct_peak": 100,
            "gpu_temperature_c_mean": 55,
            "gpu_temperature_c_p95": 59,
            "gpu_temperature_c_peak": 60,
            "gpu_graphics_clock_mhz_mean": 1700,
            "gpu_graphics_clock_mhz_p95": 1790,
            "gpu_graphics_clock_mhz_peak": 1800,
            "gpu_sm_clock_mhz_mean": 1650,
            "gpu_sm_clock_mhz_p95": 1740,
            "gpu_sm_clock_mhz_peak": 1750,
            "system_memory_used_mib_mean": 6000,
            "system_memory_used_mib_p95": 6900,
            "system_memory_used_mib_peak": 7000,
            "system_swap_used_mib_mean": 0,
            "system_swap_used_mib_p95": 0,
            "system_swap_used_mib_peak": 0,
            "electricity_krw_per_kwh": 200,
            "slo_ttft_p95_ms": 1000,
            "slo_tpot_p95_ms": 100,
            "slo_system_memory_peak_mib": 8000,
            "slo_system_swap_peak_mib": 0,
        },
        results=[
            RequestResult("1", "a", True, 200, 10.0, 50.0, 8, 5),
            RequestResult("2", "b", True, 200, 20.0, 70.0, 9, 6),
        ],
    )

    summary = summarize_run(run)

    assert summary["tpot_ms"]["p95"] == 10.0
    assert summary["request_throughput_requests_per_second"] == 2.0
    assert summary["input_throughput_tokens_per_second"] == 17.0
    assert summary["output_throughput_tokens_per_second"] == 11.0
    assert summary["total_throughput_tokens_per_second"] == 28.0
    assert summary["output_tokens_per_hour"] == 39_600.0
    assert summary["goodput_requests_per_second"] == 2.0
    assert summary["slo"]["attainment_rate"] == 1.0
    assert summary["slo"]["pass"] is True
    assert summary["gpu"]["power_w_p95"] == 22.0
    assert summary["gpu"]["memory_used_mib_mean"] == 5000.0
    assert summary["gpu"]["temperature_c_peak"] == 60.0
    assert summary["gpu"]["graphics_clock_mhz_mean"] == 1700.0
    assert summary["gpu"]["sm_clock_mhz_peak"] == 1750.0
    assert summary["system"]["memory_used_mib_peak"] == 7000.0
    assert summary["system"]["swap_used_mib_peak"] == 0.0
    assert summary["energy"]["gpu_wh_per_1k_output_tokens"] == pytest.approx(0.5050505)
    assert summary["energy"]["estimated_gpu_cost_krw_per_million_output_tokens"] == pytest.approx(
        101.0101
    )
    assert summary["energy"]["estimated_gpu_cost_krw_per_hour"] == 4.0
