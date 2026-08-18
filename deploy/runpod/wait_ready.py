from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def wait_until_ready(
    url: str,
    api_key: str,
    timeout_seconds: float,
    poll_seconds: float = 10,
) -> None:
    if timeout_seconds <= 0 or poll_seconds <= 0:
        raise ValueError("timeout and poll intervals must be positive")

    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        request = Request(url, headers={"Authorization": f"Bearer {api_key}"})
        try:
            with urlopen(request, timeout=min(10, timeout_seconds)) as response:  # noqa: S310
                if response.status == 200:
                    return
        except (HTTPError, URLError, TimeoutError):
            pass
        remaining = deadline - time.monotonic()
        if remaining > 0:
            time.sleep(min(poll_seconds, remaining))

    raise TimeoutError(f"engine did not become ready within {timeout_seconds:g} seconds")


def main() -> int:
    parser = argparse.ArgumentParser(description="RunPod engine readiness를 기다립니다.")
    parser.add_argument("--pod-file", type=Path, default=Path("pod.json"))
    parser.add_argument("--api-key", required=True)
    parser.add_argument("--timeout-seconds", type=int, default=900)
    args = parser.parse_args()

    pod = json.loads(args.pod_file.read_text(encoding="utf-8"))
    url = f"{pod['proxyUrl']}/v1/models"
    wait_until_ready(url, args.api_key, args.timeout_seconds)
    print("engine ready")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
