from __future__ import annotations

import argparse
import os
import re
import time

from deploy.runpod.client import RunPodClient

EXPIRY_PATTERN = re.compile(
    r"^qwen-serving-lab-(benchmark|staging|demo|rollback)-"
    r"[A-Za-z0-9._-]{1,80}-exp(?P<timestamp>\d+)$"
)


def is_expired_managed_pod(pod: dict[str, object], now: int) -> bool:
    match = EXPIRY_PATTERN.fullmatch(str(pod.get("name", "")))
    return bool(match and int(match.group("timestamp")) <= now)


def main() -> int:
    parser = argparse.ArgumentParser(description="만료된 qwen-serving-lab Pod를 정리합니다.")
    parser.add_argument("--apply", action="store_true", help="없으면 대상만 출력합니다.")
    args = parser.parse_args()
    client = RunPodClient(os.environ["RUNPOD_API_KEY"])
    now = int(time.time())

    for pod in client.list_pods():
        if is_expired_managed_pod(pod, now):
            pod_id = str(pod["id"])
            if args.apply:
                client.delete_pod(pod_id)
                print(f"deleted expired pod {pod_id}")
            else:
                print(f"would delete expired pod {pod_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
