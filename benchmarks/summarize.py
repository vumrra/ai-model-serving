from __future__ import annotations

import argparse
import json
import math
import statistics
from pathlib import Path
from typing import Any

from benchmarks.schema import BenchmarkRun, RequestResult


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
    tpot = [value for result in successful if (value := _tpot_ms(result)) is not None]
    prompt_tokens = sum(result.prompt_tokens or 0 for result in successful)
    completion_tokens = sum(result.completion_tokens or 0 for result in successful)
    duration_seconds = _number(run.environment.get("benchmark_duration_seconds"))
    output_tps = (
        completion_tokens / duration_seconds
        if completion_tokens and duration_seconds and duration_seconds > 0
        else None
    )
    ttft_summary = _latency_summary(ttft)
    tpot_summary = _latency_summary(tpot)
    success_rate = len(successful) / len(run.results) if run.results else 0.0
    ttft_slo = _number(run.environment.get("slo_ttft_p95_ms"))
    tpot_slo = _number(run.environment.get("slo_tpot_p95_ms"))
    gpu_peak = _number(run.environment.get("gpu_memory_used_mib_peak"))
    gpu_peak_slo = _number(run.environment.get("slo_gpu_peak_mib"))
    good_requests = sum(
        result.success
        and (ttft_slo is None or (result.ttft_ms or math.inf) <= ttft_slo)
        and (
            tpot_slo is None
            or ((result_tpot := _tpot_ms(result)) is not None and result_tpot <= tpot_slo)
        )
        for result in run.results
    )
    slo_pass = (
        success_rate == 1.0
        and _within_slo(ttft_summary["p95"], ttft_slo)
        and _within_slo(tpot_summary["p95"], tpot_slo)
        and _within_slo(gpu_peak, gpu_peak_slo)
    )

    return {
        "run_id": run.run_id,
        "engine": run.engine,
        "model": run.model,
        "workload": run.workload,
        "requests": len(run.results),
        "success_rate": success_rate,
        "ttft_ms": ttft_summary,
        "tpot_ms": tpot_summary,
        "e2e_ms": _latency_summary(e2e),
        "tokens": {
            "prompt": prompt_tokens,
            "completion": completion_tokens,
            "usage_coverage": (
                sum(result.completion_tokens is not None for result in successful) / len(successful)
                if successful
                else 0.0
            ),
        },
        "output_throughput_tokens_per_second": output_tps,
        "output_tokens_per_hour": output_tps * 3600 if output_tps is not None else None,
        "goodput_requests_per_second": (
            good_requests / duration_seconds if duration_seconds and duration_seconds > 0 else None
        ),
        "slo": {
            "ttft_p95_ms": ttft_slo,
            "tpot_p95_ms": tpot_slo,
            "gpu_peak_mib": gpu_peak_slo,
            "pass": slo_pass,
        },
        "gpu": {
            "samples": run.environment.get("gpu_samples"),
            "power_w_mean": _number(run.environment.get("gpu_power_w_mean")),
            "memory_used_mib_peak": gpu_peak,
            "utilization_pct_mean": _number(run.environment.get("gpu_utilization_pct_mean")),
        },
        "energy": _energy_summary(run.environment, duration_seconds, completion_tokens, output_tps),
    }


def _tpot_ms(result: RequestResult) -> float | None:
    if (
        result.ttft_ms is None
        or result.completion_tokens is None
        or result.completion_tokens <= 1
        or result.e2e_ms < result.ttft_ms
    ):
        return None
    return (result.e2e_ms - result.ttft_ms) / (result.completion_tokens - 1)


def _within_slo(value: float | None, limit: float | None) -> bool:
    return limit is None or (value is not None and value <= limit)


def _number(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _energy_summary(
    environment: dict[str, Any],
    duration_seconds: float | None,
    completion_tokens: int,
    output_tps: float | None,
) -> dict[str, float | None]:
    power_w = _number(environment.get("gpu_power_w_mean"))
    price = _number(environment.get("electricity_krw_per_kwh"))
    energy_wh = (
        power_w * duration_seconds / 3600
        if power_w is not None and duration_seconds is not None
        else None
    )
    wh_per_1k = (
        energy_wh * 1000 / completion_tokens
        if energy_wh is not None and completion_tokens
        else None
    )
    return {
        "estimated_gpu_energy_wh": energy_wh,
        "gpu_wh_per_1k_output_tokens": wh_per_1k,
        "estimated_gpu_cost_krw_per_million_output_tokens": (
            wh_per_1k * price if wh_per_1k is not None and price is not None else None
        ),
        "assumed_electricity_krw_per_kwh": price,
        "output_tps_for_estimate": output_tps,
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
