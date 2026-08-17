from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def main() -> int:
    parser = argparse.ArgumentParser(description="RunPod engine readiness를 기다립니다.")
    parser.add_argument("--pod-file", type=Path, default=Path("pod.json"))
    parser.add_argument("--api-key", required=True)
    parser.add_argument("--timeout-seconds", type=int, default=900)
    args = parser.parse_args()

    pod = json.loads(args.pod_file.read_text(encoding="utf-8"))
    url = f"{pod['proxyUrl']}/v1/models"
    deadline = time.monotonic() + args.timeout_seconds

    while time.monotonic() < deadline:
        request = Request(url, headers={"Authorization": f"Bearer {args.api_key}"})
        try:
            with urlopen(request, timeout=10) as response:  # noqa: S310
                if response.status == 200:
                    print("engine ready")
                    return 0
        except (HTTPError, URLError, TimeoutError):
            time.sleep(10)

    raise TimeoutError(f"{args.timeout_seconds}초 안에 engine이 준비되지 않았습니다.")


if __name__ == "__main__":
    raise SystemExit(main())
