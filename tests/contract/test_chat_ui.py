import json
from collections.abc import Iterator

import httpx
import pytest
from fastapi.testclient import TestClient

from apps.gateway.config import Settings
from apps.gateway.main import create_app


@pytest.fixture
def engine_requests() -> list[tuple[int | None, str]]:
    return []


@pytest.fixture
def client(engine_requests: list[tuple[int | None, str]]) -> Iterator[TestClient]:
    def engine(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/models":
            if request.url.port == 8004:
                raise httpx.ConnectError("MLX-LM is offline", request=request)
            return httpx.Response(200, json={"object": "list", "data": []})

        payload = json.loads(request.content)
        engine_requests.append((request.url.port, payload["model"]))
        event = {
            "id": "chatcmpl-local",
            "object": "chat.completion.chunk",
            "model": payload["model"],
            "choices": [
                {"index": 0, "delta": {"content": "선택된 엔진의 응답"}, "finish_reason": None}
            ],
        }
        body = f"data: {json.dumps(event, ensure_ascii=False)}\n\ndata: [DONE]\n\n"
        return httpx.Response(200, text=body, headers={"content-type": "text/event-stream"})

    settings = Settings(
        chat_ui_enabled=True,
        api_key="local-public-key",
        public_model_name="qwen-demo",
        rate_limit_requests=20,
    )
    app = create_app(settings, httpx.MockTransport(engine))
    with TestClient(app) as test_client:
        yield test_client


def _headers() -> dict[str, str]:
    return {"Authorization": "Bearer local-public-key"}


def _payload() -> dict:
    return {
        "model": "qwen-demo",
        "messages": [{"role": "user", "content": "안녕하세요"}],
        "stream": True,
        "max_tokens": 32,
    }


def test_chat_ui_is_served_when_enabled(client: TestClient):
    response = client.get("/")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "llama.cpp" in response.text
    assert "MLX-LM" in response.text
    assert "/ui/chat/completions" in response.text


def test_chat_ui_reports_each_local_engine_status(client: TestClient):
    response = client.get("/ui/engines", headers=_headers())

    assert response.status_code == 200
    assert response.json() == {
        "engines": [
            {"id": "llama_cpp", "name": "llama.cpp", "ready": True},
            {"id": "mlx_lm", "name": "MLX-LM", "ready": False},
            {"id": "kserve_mlx", "name": "KServe · MLX-LM", "ready": True},
        ]
    }


def test_chat_ui_streams_from_selected_engine(
    client: TestClient, engine_requests: list[tuple[int | None, str]]
):
    with client.stream(
        "POST",
        "/ui/chat/completions?engine=kserve_mlx",
        headers=_headers(),
        json=_payload(),
    ) as response:
        content = "".join(response.iter_text())

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "선택된 엔진의 응답" in content
    assert content.endswith("data: [DONE]\n\n")
    assert engine_requests == [(8005, "default_model")]


def test_chat_ui_rejects_unknown_engine(client: TestClient):
    response = client.post(
        "/ui/chat/completions?engine=http://attacker.example",
        headers=_headers(),
        json=_payload(),
    )

    assert response.status_code == 422


def test_chat_ui_is_not_served_by_default():
    with TestClient(create_app(Settings())) as client:
        assert client.get("/").status_code == 404
        assert client.get("/ui/engines").status_code == 404
