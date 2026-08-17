import asyncio

import httpx
import pytest
from fastapi import FastAPI
from fastapi.responses import StreamingResponse

from benchmarks.runner import RequestCase, run_case


@pytest.mark.asyncio
async def test_runner_records_ttft_from_sse_content() -> None:
    app = FastAPI()

    @app.post("/v1/chat/completions")
    async def completion() -> StreamingResponse:
        async def events():
            yield 'data: {"choices":[{"delta":{"role":"assistant"}}]}\n\n'
            await asyncio.sleep(0)
            yield 'data: {"choices":[{"delta":{"content":"ok"}}]}\n\n'
            yield "data: [DONE]\n\n"

        return StreamingResponse(events(), media_type="text/event-stream")

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        result = await run_case(
            client,
            "http://test/v1/chat/completions",
            RequestCase(
                prompt_id="smoke:r1",
                payload={
                    "model": "Qwen/test",
                    "messages": [{"role": "user", "content": "secret prompt"}],
                    "stream": True,
                },
            ),
            {"Content-Type": "application/json"},
        )

    assert result.success is True
    assert result.status_code == 200
    assert result.ttft_ms is not None
    assert result.e2e_ms >= result.ttft_ms
    assert "secret prompt" not in str(result)


@pytest.mark.asyncio
async def test_runner_rejects_truncated_sse() -> None:
    app = FastAPI()

    @app.post("/v1/chat/completions")
    async def completion() -> StreamingResponse:
        async def events():
            yield 'data: {"choices":[{"delta":{"content":"partial"}}]}\n\n'

        return StreamingResponse(events(), media_type="text/event-stream")

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        result = await run_case(
            client,
            "http://test/v1/chat/completions",
            RequestCase(
                prompt_id="truncated:r1",
                payload={"model": "Qwen/test", "messages": [], "stream": True},
            ),
            {"Content-Type": "application/json"},
        )

    assert result.success is False
    assert result.error == "truncated_stream"
