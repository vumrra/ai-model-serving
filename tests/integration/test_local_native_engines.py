from __future__ import annotations

import json
import os
import socket
import subprocess
import time
from pathlib import Path

import httpx
import pytest

from scripts.run_local_engine import resolve_engine_command


def _unused_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def _wait_until_ready(client: httpx.Client, process: subprocess.Popen[bytes]) -> None:
    deadline = time.monotonic() + 180
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"engine exited before readiness with code {process.returncode}")
        try:
            response = client.get("/v1/models")
            if response.status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(0.25)
    raise RuntimeError("engine was not ready within 180 seconds")


def _assert_json_and_sse_contract(base_url: str, model: str, engine: str) -> None:
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "1 더하기 1은?"}],
        "max_tokens": 16,
        "temperature": 0,
        "chat_template_kwargs": {"enable_thinking": False},
    }
    with httpx.Client(base_url=base_url, timeout=120) as client:
        json_started = time.perf_counter()
        response = client.post("/v1/chat/completions", json=payload)
        response.raise_for_status()
        json_elapsed = time.perf_counter() - json_started
        content = response.json()["choices"][0]["message"]["content"]
        assert isinstance(content, str) and content.strip()

        payload["stream"] = True
        stream_started = time.perf_counter()
        first_content_at: float | None = None
        done = False
        with client.stream("POST", "/v1/chat/completions", json=payload) as stream:
            stream.raise_for_status()
            for line in stream.iter_lines():
                if not line.startswith("data:"):
                    continue
                data = line.removeprefix("data:").strip()
                if data == "[DONE]":
                    done = True
                    continue
                chunk = json.loads(data)
                if any(choice.get("delta", {}).get("content") for choice in chunk["choices"]):
                    first_content_at = first_content_at or time.perf_counter()
        assert first_content_at is not None
        assert done
        stream_elapsed = time.perf_counter() - stream_started

    print(
        f"{engine}: json_e2e={json_elapsed * 1000:.1f}ms "
        f"stream_ttft={(first_content_at - stream_started) * 1000:.1f}ms "
        f"stream_e2e={stream_elapsed * 1000:.1f}ms"
    )


def _run_smoke(engine: str, model: str) -> None:
    port = _unused_port()
    command = resolve_engine_command(engine, Path("models/manifest.yaml"), port=port)
    process = subprocess.Popen(command)
    try:
        base_url = f"http://127.0.0.1:{port}"
        with httpx.Client(base_url=base_url, timeout=1) as client:
            _wait_until_ready(client, process)
        _assert_json_and_sse_contract(base_url, model, engine)
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


@pytest.mark.skipif(
    os.getenv("RUN_LLAMA_MODEL_SMOKE") != "1",
    reason="set RUN_LLAMA_MODEL_SMOKE=1 to run the real llama.cpp model",
)
def test_llama_cpp_serves_json_and_sse() -> None:
    _run_smoke("llama_cpp", "qwen3-0.6b")


@pytest.mark.skipif(
    os.getenv("RUN_MLX_MODEL_SMOKE") != "1",
    reason="set RUN_MLX_MODEL_SMOKE=1 to run the real MLX-LM model",
)
def test_mlx_lm_serves_json_and_sse() -> None:
    _run_smoke("mlx_lm", "default_model")
