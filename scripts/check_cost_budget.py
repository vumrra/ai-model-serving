from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="GPU 예산과 시간 상한을 검사합니다.")
    parser.add_argument("--cost-per-hour", type=float, required=True)
    parser.add_argument("--planned-hours", type=float, required=True)
    parser.add_argument("--budget", type=float, default=30.0)
    parser.add_argument("--used-cost", type=float, default=0.0)
    parser.add_argument("--output", type=Path, default=Path("cost-report.json"))
    args = parser.parse_args()

    if min(args.cost_per_hour, args.planned_hours, args.budget) <= 0:
        raise ValueError("시간당 비용, 계획 시간, 예산은 0보다 커야 합니다.")
    if args.used_cost < 0:
        raise ValueError("이미 사용한 비용은 음수일 수 없습니다.")

    expected = args.cost_per_hour * args.planned_hours
    remaining = args.budget - args.used_cost
    report = {
        "cost_per_hour": args.cost_per_hour,
        "planned_hours": args.planned_hours,
        "expected_cost": round(expected, 4),
        "remaining_budget": round(remaining, 4),
        "approved": expected <= remaining,
    }
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")

    if not report["approved"]:
        raise SystemExit("예상 GPU 비용이 남은 예산을 넘습니다.")
    print(f"approved: expected ${expected:.2f}, remaining ${remaining:.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
