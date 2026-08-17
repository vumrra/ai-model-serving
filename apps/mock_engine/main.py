from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import os
import re
from dataclasses import dataclass
from typing import Any, Literal

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field


@dataclass(frozen=True, slots=True)
class MockSettings:
    model_name: str = "mock-qwen"
    api_key: str = "mock-internal-key"
    token_delay_seconds: float = 0.0

    @classmethod
    def from_env(cls) -> MockSettings:
        defaults = cls()
        return cls(
            model_name=os.getenv("MOCK_MODEL_NAME", defaults.model_name),
            api_key=os.getenv("ENGINE_API_KEY", os.getenv("MOCK_ENGINE_API_KEY", defaults.api_key)),
            token_delay_seconds=float(
                os.getenv("MOCK_TOKEN_DELAY_SECONDS", str(defaults.token_delay_seconds))
            ),
        )


class MockMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["system", "user", "assistant"]
    content: str = Field(min_length=1)


class MockChatRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    model: str
    messages: list[MockMessage] = Field(min_length=1)
    stream: bool = False
    max_tokens: int = Field(default=256, ge=1)


def _tokens(text: str) -> list[str]:
    return re.findall(r"\S+\s*", text)


def _usage(messages: list[MockMessage], answer: str) -> dict[str, int]:
    prompt_tokens = sum(len(_tokens(message.content)) for message in messages)
    completion_tokens = len(_tokens(answer))
    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": prompt_tokens + completion_tokens,
    }


def _error(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={
            "error": {
                "message": message,
                "type": "invalid_request_error",
                "code": code,
            }
        },
    )


def create_app(settings: MockSettings | None = None) -> FastAPI:
    settings = settings or MockSettings.from_env()
    application = FastAPI(title="mock-qwen-engine", version="0.1.0")

    @application.exception_handler(HTTPException)
    async def openai_error(_request: Request, exc: HTTPException) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content=exc.detail)

    def authorize(authorization: str | None) -> None:
        scheme, _, token = (authorization or "").partition(" ")
        if (
            scheme.lower() != "bearer"
            or not token
            or not hmac.compare_digest(token, settings.api_key)
        ):
            raise _error(401, "invalid_api_key", "Invalid upstream API key.")

    @application.get("/livez")
    async def livez() -> dict[str, str]:
        return {"status": "ok"}

    @application.get("/v1/models")
    async def models(authorization: str | None = Header(default=None)) -> dict[str, Any]:
        authorize(authorization)
        return {
            "object": "list",
            "data": [
                {
                    "id": settings.model_name,
                    "object": "model",
                    "owned_by": "qwen-serving-lab",
                }
            ],
        }

    @application.post("/v1/chat/completions")
    async def chat_completions(
        payload: MockChatRequest,
        authorization: str | None = Header(default=None),
    ) -> Any:
        authorize(authorization)
        if payload.model != settings.model_name:
            raise _error(404, "model_not_found", "Requested model is not served.")

        last_user = next(
            (message.content for message in reversed(payload.messages) if message.role == "user"),
            payload.messages[-1].content,
        )
        answer = f"모의 Qwen 응답: {last_user}"
        completion_id = "chatcmpl-mock-" + hashlib.sha256(last_user.encode()).hexdigest()[:12]
        answer_tokens = _tokens(answer)[: payload.max_tokens]
        answer = "".join(answer_tokens).rstrip()

        if payload.stream:

            async def events():
                first = {
                    "id": completion_id,
                    "object": "chat.completion.chunk",
                    "created": 0,
                    "model": settings.model_name,
                    "choices": [
                        {"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}
                    ],
                }
                yield f"data: {json.dumps(first, ensure_ascii=False)}\n\n"
                for token in answer_tokens:
                    if settings.token_delay_seconds:
                        await asyncio.sleep(settings.token_delay_seconds)
                    chunk = {
                        "id": completion_id,
                        "object": "chat.completion.chunk",
                        "created": 0,
                        "model": settings.model_name,
                        "choices": [
                            {
                                "index": 0,
                                "delta": {"content": token},
                                "finish_reason": None,
                            }
                        ],
                    }
                    yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
                final = {
                    "id": completion_id,
                    "object": "chat.completion.chunk",
                    "created": 0,
                    "model": settings.model_name,
                    "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
                }
                yield f"data: {json.dumps(final, ensure_ascii=False)}\n\n"
                yield "data: [DONE]\n\n"

            return StreamingResponse(events(), media_type="text/event-stream")

        return {
            "id": completion_id,
            "object": "chat.completion",
            "created": 0,
            "model": settings.model_name,
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": answer},
                    "finish_reason": "stop",
                }
            ],
            "usage": _usage(payload.messages, answer),
        }

    return application


app = create_app()
