from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from engines.transformers.app import create_app
from scripts.run_transformers_cpu import smoke_environment

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_CPU_MODEL_SMOKE") != "1",
    reason="set RUN_CPU_MODEL_SMOKE=1 to download and run the real Qwen CPU model",
)


def test_real_qwen_cpu_serves_json_and_sse(monkeypatch: pytest.MonkeyPatch) -> None:
    for name, value in smoke_environment(Path("models/manifest.yaml")).items():
        monkeypatch.setenv(name, value)

    payload = {
        "model": "Qwen/Qwen3-0.6B",
        "messages": [{"role": "user", "content": "1 더하기 1은?"}],
        "max_tokens": 8,
        "temperature": 0,
        "chat_template_kwargs": {"enable_thinking": False},
    }
    with TestClient(create_app()) as client:
        assert client.get("/readyz").json() == {
            "status": "ready",
            "model": "Qwen/Qwen3-0.6B",
        }
        assert client.get("/v1/models").json()["data"][0]["id"] == "Qwen/Qwen3-0.6B"

        response = client.post("/v1/chat/completions", json=payload)
        assert response.status_code == 200
        assert response.json()["model"] == "Qwen/Qwen3-0.6B"
        assert response.json()["usage"]["completion_tokens"] > 0

        payload["stream"] = True
        with client.stream("POST", "/v1/chat/completions", json=payload) as stream:
            body = "".join(stream.iter_text())
        assert stream.status_code == 200
        assert stream.headers["content-type"].startswith("text/event-stream")
        assert '"content":' in body
        assert "data: [DONE]" in body
