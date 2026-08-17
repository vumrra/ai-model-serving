from scripts.check_benchmark_gate import check_gate


def test_benchmark_gate_rejects_slow_result():
    summary = {
        "success_rate": 1.0,
        "ttft_ms": {"p95": 6_000},
        "e2e_ms": {"p95": 20_000},
    }

    assert check_gate(summary, 0.99, 5_000, 30_000) == ["ttft_p95"]
