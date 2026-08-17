from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from deploy.runpod.client import RunPodClient


def main() -> int:
    parser = argparse.ArgumentParser(description="RunPod Pod를 완전히 종료합니다.")
    parser.add_argument("--pod-id")
    parser.add_argument("--pod-file", type=Path)
    args = parser.parse_args()

    pod_id = args.pod_id
    if args.pod_file:
        pod_id = str(json.loads(args.pod_file.read_text(encoding="utf-8"))["id"])
    if not pod_id:
        parser.error("--pod-id 또는 --pod-file이 필요합니다.")

    RunPodClient(os.environ["RUNPOD_API_KEY"]).delete_pod(pod_id)
    print(f"deleted {pod_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
