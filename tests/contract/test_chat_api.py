import json
from collections.abc import Iterator
from dataclasses import replace

import httpx
import pytest
from fastapi.testclient import TestClient

from apps.gateway.config import Settings
from apps.gateway.main import create_app as create_gateway
from apps.mock_engine.main import MockSettings
from apps.mock_engine.main import create_app as create_mock_engine


@pytest.fixture
def settings() -> Settings:
    return Settings(
        api_key="test-client-key",
        upstream_api_key="test-upstream-key",
        public_model_name="qwen-demo",
        upstream_model_name="mock-qwen",
        upstream_base_url="http://mock-engine",
        release_id="test-release",
        git_sha="abc123",
        rate_limit_requests=20,
    )


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    mock = create_mock_engine(MockSettings(model_name="mock-qwen", api_key="test-upstream-key"))
    gateway = create_gateway(settings, httpx.ASGITransport(app=mock))
    with TestClient(gateway) as test_client:
        yield test_client


def _headers() -> dict[str, str]:
    return {
        "Authorization": "Bearer test-client-key",
        "X-Request-ID": "request-from-test",
    }


def _payload(stream: bool = False) -> dict:
    return {
        "model": "qwen-demo",
        "messages": [{"role": "user", "content": "안녕하세요"}],
        "stream": stream,
        "max_tokens": 32,
    }


def test_non_stream_completion_is_openai_compatible(client: TestClient):
    response = client.post("/v1/chat/completions", headers=_headers(), json=_payload())

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "request-from-test"
    body = response.json()
    assert body["object"] == "chat.completion"
    assert body["model"] == "qwen-demo"
    assert body["choices"][0]["message"] == {
        "role": "assistant",
        "content": "모의 Qwen 응답: 안녕하세요",
    }
    assert body["choices"][0]["finish_reason"] == "stop"
    assert body["usage"]["total_tokens"] > 0


def test_models_lists_public_alias_and_requires_auth(client: TestClient):
    unauthorized = client.get("/v1/models")
    response = client.get("/v1/models", headers=_headers())

    assert unauthorized.status_code == 401
    assert response.status_code == 200
    assert response.json() == {
        "object": "list",
        "data": [
            {
                "id": "qwen-demo",
                "object": "model",
                "created": 0,
                "owned_by": "qwen-serving-lab",
            }
        ],
    }


def test_gateway_disables_thinking_for_upstream(settings: Settings):
    payloads: list[dict] = []

    def upstream(request: httpx.Request) -> httpx.Response:
        payloads.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "object": "chat.completion",
                "model": "mock-qwen",
                "choices": [],
            },
        )

    gateway = create_gateway(
        replace(settings, enable_thinking=False),
        httpx.MockTransport(upstream),
    )
    with TestClient(gateway) as test_client:
        response = test_client.post("/v1/chat/completions", headers=_headers(), json=_payload())

    assert response.status_code == 200
    assert payloads[0]["chat_template_kwargs"] == {"enable_thinking": False}


def test_stream_completion_ends_with_done(client: TestClient):
    with client.stream(
        "POST",
        "/v1/chat/completions",
        headers=_headers(),
        json=_payload(stream=True),
    ) as response:
        content = "".join(response.iter_text())

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert '"object": "chat.completion.chunk"' in content
    assert '"model": "qwen-demo"' in content
    assert "모의" in content
    assert content.endswith("data: [DONE]\n\n")


def test_authentication_error_uses_standard_shape(client: TestClient):
    response = client.post("/v1/chat/completions", json=_payload())

    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"
    error = response.json()["error"]
    assert error["code"] == "invalid_api_key"
    assert error["type"] == "authentication_error"
    assert error["request_id"].startswith("req_")


def test_request_limits_are_enforced(settings: Settings):
    limited = replace(settings, max_messages=1, max_completion_tokens=8)
    mock = create_mock_engine(MockSettings(model_name="mock-qwen", api_key="test-upstream-key"))
    gateway = create_gateway(limited, httpx.ASGITransport(app=mock))

    with TestClient(gateway) as test_client:
        payload = _payload()
        payload["messages"].append({"role": "user", "content": "두 번째"})
        response = test_client.post("/v1/chat/completions", headers=_headers(), json=payload)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "too_many_messages"


def test_rate_limit_returns_retry_after(settings: Settings):
    limited = replace(settings, rate_limit_requests=1)
    mock = create_mock_engine(MockSettings(model_name="mock-qwen", api_key="test-upstream-key"))
    gateway = create_gateway(limited, httpx.ASGITransport(app=mock))

    with TestClient(gateway) as test_client:
        first = test_client.post("/v1/chat/completions", headers=_headers(), json=_payload())
        second = test_client.post("/v1/chat/completions", headers=_headers(), json=_payload())

    assert first.status_code == 200
    assert second.status_code == 429
    assert int(second.headers["Retry-After"]) > 0
    assert second.json()["error"]["code"] == "rate_limit_exceeded"


def test_health_readiness_and_version(client: TestClient):
    assert client.get("/livez").json() == {"status": "ok"}
    assert client.get("/readyz").json() == {"status": "ready"}

    version = client.get("/version")
    assert version.status_code == 200
    assert version.json() == {
        "service": "qwen-serving-gateway",
        "version": "0.1.0",
        "release_id": "test-release",
        "git_sha": "abc123",
        "engine": "mock",
        "model": "qwen-demo",
        "model_revision": "unknown",
        "gateway_image": "unknown",
        "runtime_image": "unknown",
        "serving_config_sha256": "unknown",
    }

    metrics = client.get("/metrics")
    assert metrics.status_code == 200
    assert "qwen_http_requests_total" in metrics.text
    assert "qwen_engine_ready 1.0" in metrics.text


def test_upstream_timeout_is_standardized(settings: Settings):
    def timeout_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("too slow", request=request)

    gateway = create_gateway(settings, httpx.MockTransport(timeout_handler))

    with TestClient(gateway) as test_client:
        response = test_client.post("/v1/chat/completions", headers=_headers(), json=_payload())

    assert response.status_code == 504
    assert response.json()["error"]["code"] == "upstream_timeout"


def test_stream_upstream_error_is_standardized(settings: Settings):
    mock = create_mock_engine(MockSettings(model_name="mock-qwen", api_key="different-key"))
    gateway = create_gateway(settings, httpx.ASGITransport(app=mock))

    with TestClient(gateway) as test_client:
        response = test_client.post(
            "/v1/chat/completions",
            headers=_headers(),
            json=_payload(stream=True),
        )

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "upstream_rejected"
