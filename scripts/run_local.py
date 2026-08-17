from __future__ import annotations

import os
import signal
import subprocess
import sys
import time


def start(module: str, port: int, env: dict[str, str]) -> subprocess.Popen[str]:
    """Uvicorn 프로세스 하나를 시작합니다."""

    return subprocess.Popen(
        [sys.executable, "-m", "uvicorn", module, "--port", str(port)],
        env=env,
        text=True,
    )


def main() -> int:
    env = os.environ.copy()
    env.setdefault("PUBLIC_API_KEY", "local-public-key")
    env.setdefault("ENGINE_API_KEY", "local-engine-key")
    env.setdefault("ENGINE_BASE_URL", "http://127.0.0.1:8001")
    env.setdefault("ENGINE_MODEL_NAME", "mock-qwen")
    env.setdefault("MODEL_ALIAS", "qwen3-4b")
    env.setdefault("RELEASE_ID", "local-mock")

    processes = [
        start("apps.mock_engine.main:app", 8001, env),
        start("apps.gateway.main:app", 8000, env),
    ]

    def stop_all(_signum: int, _frame: object) -> None:
        for process in processes:
            process.terminate()

    signal.signal(signal.SIGINT, stop_all)
    signal.signal(signal.SIGTERM, stop_all)

    try:
        while all(process.poll() is None for process in processes):
            time.sleep(0.2)
    finally:
        stop_all(0, None)
        for process in processes:
            process.wait(timeout=5)

    return next((process.returncode for process in processes if process.returncode), 0)


if __name__ == "__main__":
    raise SystemExit(main())
