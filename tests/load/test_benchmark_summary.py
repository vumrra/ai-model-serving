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
