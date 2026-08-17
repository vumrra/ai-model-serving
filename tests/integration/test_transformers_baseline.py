from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi.testclient import TestClient

from engines.transformers.app import ChatCompletionRequest, Generation, create_app


class FakeBackend:
    model_name = "Qwen/test"

    async def generate(self, request: ChatCompletionRequest) -> Generation:
        return Generation(
            text="42",
            prompt_tokens=5,
            completion_tokens=1,
            finish_reason="stop",
        )

    async def stream(self, request: ChatCompletionRequest) -> AsyncIterator[str]:
        yield "4"
        yield "2"

    def count_tokens(self, text: str) -> int:
        return 1


def request_body(stream: bool) -> dict[str, object]:
    return {
        "model": "Qwen/test",
        "messages": [{"role": "user", "content": "12 + 30?"}],
        "max_tokens": 8,
        "temperature": 0,
        "stream": stream,
    }


def test_json_chat_completion_contract() -> None:
    with TestClient(create_app(FakeBackend())) as client:
        response = client.post("/v1/chat/completions", json=request_body(False))

    assert response.status_code == 200
    body = response.json()
    assert body["object"] == "chat.completion"
    assert body["choices"][0]["message"] == {"role": "assistant", "content": "42"}
    assert body["usage"]["total_tokens"] == 6


def test_sse_chat_completion_contract() -> None:
    with TestClient(create_app(FakeBackend())) as client:
        with client.stream("POST", "/v1/chat/completions", json=request_body(True)) as response:
            body = "".join(response.iter_text())

    assert response.status_code == 200
    assert '"content": "4"' in body
    assert '"content": "2"' in body
    assert "data: [DONE]" in body
