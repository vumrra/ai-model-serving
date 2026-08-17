from __future__ import annotations

import argparse
import json
import math
import statistics
from pathlib import Path
from typing import Any

from benchmarks.schema import BenchmarkRun


def percentile(values: list[float], quantile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * quantile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def summarize_run(run: BenchmarkRun) -> dict[str, Any]:
    successful = [result for result in run.results if result.success]
    ttft = [result.ttft_ms for result in successful if result.ttft_ms is not None]
    e2e = [result.e2e_ms for result in successful]
    return {
        "run_id": run.run_id,
        "engine": run.engine,
        "model": run.model,
        "workload": run.workload,
        "requests": len(run.results),
        "success_rate": len(successful) / len(run.results) if run.results else 0.0,
        "ttft_ms": _latency_summary(ttft),
        "e2e_ms": _latency_summary(e2e),
    }


def _latency_summary(values: list[float]) -> dict[str, float | None]:
    return {
        "mean": statistics.fmean(values) if values else None,
        "p50": percentile(values, 0.50),
        "p95": percentile(values, 0.95),
        "p99": percentile(values, 0.99),
    }


def load_run(path: Path) -> BenchmarkRun:
    return BenchmarkRun.from_dict(json.loads(path.read_text(encoding="utf-8")))


def main() -> int:
    parser = argparse.ArgumentParser(description="벤치마크 결과 JSON 요약")
    parser.add_argument("results", nargs="+", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    summaries = [summarize_run(load_run(path)) for path in args.results]
    document = json.dumps(summaries, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(document, encoding="utf-8")
    else:
        print(document, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
