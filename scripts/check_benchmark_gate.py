from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from benchmarks.schema import BenchmarkRun
from benchmarks.summarize import summarize_run


def check_gate(
    result: dict[str, Any],
    min_success_rate: float,
    max_ttft_ms: float,
    max_e2e_ms: float,
) -> list[str]:
    failures: list[str] = []
    if float(result["success_rate"]) < min_success_rate:
        failures.append("success_rate")
    ttft = result["ttft_ms"]
    e2e = result["e2e_ms"]
    assert isinstance(ttft, dict)
    assert isinstance(e2e, dict)
    if ttft["p95"] is None or float(ttft["p95"]) > max_ttft_ms:
        failures.append("ttft_p95")
    if e2e["p95"] is None or float(e2e["p95"]) > max_e2e_ms:
        failures.append("e2e_p95")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description="승격 전에 benchmark SLO를 검사합니다.")
    parser.add_argument("result", type=Path)
    parser.add_argument("--min-success-rate", type=float, default=0.99)
    parser.add_argument("--max-ttft-ms", type=float, default=5_000)
    parser.add_argument("--max-e2e-ms", type=float, default=30_000)
    args = parser.parse_args()

    run = BenchmarkRun.from_dict(json.loads(args.result.read_text(encoding="utf-8")))
    failures = check_gate(
        summarize_run(run),
        args.min_success_rate,
        args.max_ttft_ms,
        args.max_e2e_ms,
    )
    if failures:
        raise SystemExit(f"benchmark gate failed: {', '.join(failures)}")
    print("benchmark SLO gate passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
