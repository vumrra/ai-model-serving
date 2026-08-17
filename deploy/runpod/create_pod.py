from __future__ import annotations

import argparse
import json
import os
import re
import time
from pathlib import Path

from deploy.runpod.client import RunPodClient

_SAFE_NAME = re.compile(r"^[A-Za-z0-9._-]{1,80}$")
_SAFE_SECRET_NAME = re.compile(r"^[A-Za-z0-9_-]{1,80}$")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="TTL이 있는 RunPod GPU Pod를 생성합니다.")
    parser.add_argument("--image", required=True, help="tag가 아닌 OCI image digest")
    parser.add_argument("--release-id", required=True)
    parser.add_argument("--gpu", default="NVIDIA L40S")
    parser.add_argument(
        "--purpose",
        choices=["benchmark", "staging", "demo", "rollback"],
        default="staging",
    )
    parser.add_argument("--ttl-minutes", type=int, default=45)
    parser.add_argument("--max-hourly-cost", type=float, default=1.25)
    parser.add_argument("--max-job-cost", type=float, default=5.0)
    parser.add_argument("--output", type=Path, default=Path("pod.json"))
    return parser.parse_args()


def build_payload(args: argparse.Namespace) -> dict[str, object]:
    if not 1 <= args.ttl_minutes <= 240:
        raise ValueError("ttl-minutes는 1 이상 240 이하여야 합니다.")
    if not _SAFE_NAME.fullmatch(args.release_id):
        raise ValueError("release-id는 영문, 숫자, 점, 밑줄, 대시만 사용할 수 있습니다.")
    secret_name = os.getenv("RUNPOD_ENGINE_SECRET_NAME", "qwen_engine_api_key")
    if not _SAFE_SECRET_NAME.fullmatch(secret_name):
        raise ValueError("RunPod secret 이름 형식이 올바르지 않습니다.")

    expires_at = int(time.time() + args.ttl_minutes * 60)
    payload: dict[str, object] = {
        "name": f"qwen-serving-lab-{args.purpose}-{args.release_id}-exp{expires_at}",
        "cloudType": "SECURE",
        "computeType": "GPU",
        "gpuTypeIds": [args.gpu],
        "gpuCount": 1,
        "gpuTypePriority": "availability",
        "imageName": args.image,
        "containerDiskInGb": 50,
        "volumeInGb": 30,
        "volumeMountPath": "/workspace",
        "ports": ["8000/http"],
        "interruptible": False,
        "env": {
            "MODEL_ID": os.environ["MODEL_ID"],
            "MODEL_REVISION": os.environ["MODEL_REVISION"],
            "DTYPE": os.environ["MODEL_DTYPE"],
            "MAX_MODEL_LEN": os.environ["MAX_MODEL_LEN"],
            "TENSOR_PARALLEL_SIZE": os.environ["TENSOR_PARALLEL_SIZE"],
            "GPU_MEMORY_UTILIZATION": os.environ["GPU_MEMORY_UTILIZATION"],
            "ENGINE_API_KEY": f"{{{{ RUNPOD_SECRET_{secret_name} }}}}",
            "RELEASE_ID": args.release_id,
        },
    }
    if registry_auth_id := os.getenv("RUNPOD_REGISTRY_AUTH_ID"):
        payload["containerRegistryAuthId"] = registry_auth_id
    return payload


def sanitize_pod(pod: dict[str, object], payload: dict[str, object]) -> dict[str, object]:
    pod_id = str(pod["id"])
    name = str(payload["name"])
    return {
        "id": pod_id,
        "name": name,
        "proxyUrl": f"https://{pod_id}-8000.proxy.runpod.net",
        "costPerHr": pod.get("costPerHr"),
        "adjustedCostPerHr": pod.get("adjustedCostPerHr"),
        "expiresAt": int(name.rsplit("-exp", 1)[1]),
    }


def main() -> int:
    args = parse_args()
    if args.max_hourly_cost <= 0 or args.max_job_cost <= 0:
        raise ValueError("비용 상한은 0보다 커야 합니다.")
    client = RunPodClient(os.environ["RUNPOD_API_KEY"])
    payload = build_payload(args)
    pod = client.create_pod(payload)
    hourly_cost = float(pod.get("costPerHr", pod.get("adjustedCostPerHr", 0)))
    expected_cost = hourly_cost * args.ttl_minutes / 60

    if hourly_cost <= 0 or hourly_cost > args.max_hourly_cost or expected_cost > args.max_job_cost:
        client.delete_pod(str(pod["id"]))
        raise RuntimeError(
            f"GPU 비용 ${hourly_cost:.2f}/h, 총 ${expected_cost:.2f}가 상한을 벗어납니다."
        )

    summary = sanitize_pod(pod, payload)
    args.output.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(summary["proxyUrl"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
