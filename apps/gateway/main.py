from __future__ import annotations

import asyncio
import hashlib
import hmac
import re
import uuid
from collections.abc import AsyncIterator
from dataclasses import replace
from pathlib import Path
from typing import Any, Literal

import httpx
from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse

from apps.gateway.config import Settings
from apps.gateway.errors import GatewayError
from apps.gateway.metrics import GatewayMetrics, metric_path
from apps.gateway.rate_limit import InMemoryRateLimiter
from apps.gateway.schemas import (
    ChatCompletionRequest,
    HealthResponse,
    VersionResponse,
)
from apps.gateway.upstream import UpstreamClient

_REQUEST_ID = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
_CHAT_UI = Path(__file__).with_name("chat.html")
_LOCAL_ENGINES = {
    "llama_cpp": ("llama.cpp", "http://127.0.0.1:8003", "qwen3-0.6b"),
    "mlx_lm": ("MLX-LM", "http://127.0.0.1:8004", "default_model"),
    "kserve_vllm": ("KServe · vLLM CPU", "http://127.0.0.1:8005", "qwen3-4b"),
}


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "unknown")


def _error_payload(request: Request, code: str, message: str, error_type: str) -> dict[str, Any]:
    return {
        "error": {
            "message": message,
            "type": error_type,
            "code": code,
            "request_id": _request_id(request),
        }
    }


def _validate_request(payload: ChatCompletionRequest, settings: Settings) -> None:
    if payload.model != settings.public_model_name:
        raise GatewayError(
            404,
            "model_not_found",
            f"Model '{payload.model}' is not served.",
            "invalid_request_error",
        )
    if len(payload.messages) > settings.max_messages:
        raise GatewayError(
            422,
            "too_many_messages",
            f"At most {settings.max_messages} messages are allowed.",
            "invalid_request_error",
        )
    prompt_chars = sum(len(message.content) for message in payload.messages)
    if prompt_chars > settings.max_prompt_chars:
        raise GatewayError(
            422,
            "prompt_too_large",
            f"Prompt must not exceed {settings.max_prompt_chars} characters.",
            "invalid_request_error",
        )
    if payload.max_tokens > settings.max_completion_tokens:
        raise GatewayError(
            422,
            "max_tokens_exceeded",
            f"max_tokens must not exceed {settings.max_completion_tokens}.",
            "invalid_request_error",
        )


def create_app(
    settings: Settings | None = None,
    upstream_transport: httpx.AsyncBaseTransport | None = None,
) -> FastAPI:
    settings = settings or Settings.from_env()
    application = FastAPI(title=settings.service_name, version=settings.service_version)
    application.state.settings = settings
    application.state.limiter = InMemoryRateLimiter(
        settings.rate_limit_requests, settings.rate_limit_window_seconds
    )
    application.state.metrics = GatewayMetrics()
    application.state.upstream = UpstreamClient(
        settings, upstream_transport, application.state.metrics
    )
    application.state.ui_upstreams = {
        engine: UpstreamClient(
            replace(
                settings,
                upstream_base_url=base_url,
                upstream_model_name=model,
                upstream_api_key="",
            ),
            upstream_transport,
            application.state.metrics,
        )
        for engine, (_, base_url, model) in _LOCAL_ENGINES.items()
    }

    @application.middleware("http")
    async def request_context(request: Request, call_next: Any) -> JSONResponse:
        supplied = request.headers.get("X-Request-ID", "")
        request.state.request_id = (
            supplied if _REQUEST_ID.fullmatch(supplied) else f"req_{uuid.uuid4().hex}"
        )

        content_length = request.headers.get("Content-Length")
        if content_length:
            try:
                too_large = int(content_length) > settings.max_body_bytes
            except ValueError:
                too_large = True
            if too_large:
                response = JSONResponse(
                    status_code=413,
                    content=_error_payload(
                        request,
                        "body_too_large",
                        f"Request body must not exceed {settings.max_body_bytes} bytes.",
                        "invalid_request_error",
                    ),
                )
                response.headers["X-Request-ID"] = request.state.request_id
                return response

        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        application.state.metrics.requests.labels(
            request.method,
            metric_path(request.url.path),
            str(response.status_code),
        ).inc()
        return response

    @application.exception_handler(GatewayError)
    async def gateway_error_handler(request: Request, exc: GatewayError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=_error_payload(request, exc.code, exc.message, exc.error_type),
            headers=exc.headers,
        )

    @application.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        first_error = exc.errors()[0] if exc.errors() else {}
        message = str(first_error.get("msg", "Request validation failed."))
        return JSONResponse(
            status_code=422,
            content=_error_payload(request, "invalid_request", message, "invalid_request_error"),
        )

    async def authorize_and_limit(request: Request) -> str:
        authorization = request.headers.get("Authorization", "")
        scheme, _, token = authorization.partition(" ")
        if (
            scheme.lower() != "bearer"
            or not token
            or not hmac.compare_digest(token, settings.api_key)
        ):
            raise GatewayError(
                401,
                "invalid_api_key",
                "A valid Bearer API key is required.",
                "authentication_error",
                {"WWW-Authenticate": "Bearer"},
            )

        key_id = hashlib.sha256(token.encode()).hexdigest()
        allowed, retry_after = await application.state.limiter.allow(key_id)
        if not allowed:
            raise GatewayError(
                429,
                "rate_limit_exceeded",
                "Rate limit exceeded. Try again later.",
                "rate_limit_error",
                {"Retry-After": str(retry_after)},
            )
        return key_id

    @application.get("/livez", response_model=HealthResponse)
    async def livez() -> HealthResponse:
        return HealthResponse(status="ok")

    @application.get("/readyz", response_model=HealthResponse)
    async def readyz() -> HealthResponse:
        if not await application.state.upstream.is_ready():
            application.state.metrics.engine_ready.set(0)
            raise GatewayError(
                503,
                "not_ready",
                "Inference engine is not ready.",
                "service_unavailable",
            )
        application.state.metrics.engine_ready.set(1)
        return HealthResponse(status="ready")

    @application.get("/metrics")
    async def metrics() -> Response:
        return Response(
            application.state.metrics.render(),
            media_type="text/plain; version=0.0.4; charset=utf-8",
        )

    @application.get("/version", response_model=VersionResponse)
    async def version() -> VersionResponse:
        return VersionResponse(
            service=settings.service_name,
            version=settings.service_version,
            release_id=settings.release_id,
            git_sha=settings.git_sha,
            engine=settings.engine_name,
            model=settings.public_model_name,
            model_revision=settings.model_revision,
            gateway_image=settings.gateway_image,
            runtime_image=settings.runtime_image,
            serving_config_sha256=settings.serving_config_sha256,
        )

    @application.get("/v1/models")
    async def models(_: str = Depends(authorize_and_limit)) -> dict[str, Any]:
        return {
            "object": "list",
            "data": [
                {
                    "id": settings.public_model_name,
                    "object": "model",
                    "created": 0,
                    "owned_by": "qwen-serving-lab",
                }
            ],
        }

    async def proxy_completion(
        payload: ChatCompletionRequest,
        request: Request,
        upstream: UpstreamClient,
    ) -> Any:
        upstream_payload = payload.model_dump()
        upstream_payload["model"] = upstream.settings.upstream_model_name
        upstream_payload["chat_template_kwargs"] = {
            "enable_thinking": upstream.settings.enable_thinking
        }
        request_id = _request_id(request)
        application.state.metrics.active.inc()

        if payload.stream:
            try:
                iterator = await upstream.stream(upstream_payload, request_id, request)
            except Exception:
                application.state.metrics.active.dec()
                raise

            async def tracked() -> AsyncIterator[bytes]:
                try:
                    async for chunk in iterator:
                        yield chunk
                finally:
                    application.state.metrics.active.dec()

            return StreamingResponse(
                tracked(),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "X-Accel-Buffering": "no",
                },
            )

        try:
            result = await upstream.complete(upstream_payload, request_id)
            result["model"] = settings.public_model_name
            return JSONResponse(result)
        finally:
            application.state.metrics.active.dec()

    if settings.chat_ui_enabled:

        @application.get("/", include_in_schema=False)
        async def chat_ui() -> FileResponse:
            return FileResponse(_CHAT_UI, media_type="text/html")

        @application.get("/ui/engines", include_in_schema=False)
        async def ui_engines(_: str = Depends(authorize_and_limit)) -> dict[str, Any]:
            ready = await asyncio.gather(
                *(upstream.is_ready() for upstream in application.state.ui_upstreams.values())
            )
            return {
                "engines": [
                    {"id": engine, "name": config[0], "ready": status}
                    for (engine, config), status in zip(_LOCAL_ENGINES.items(), ready, strict=True)
                ]
            }

        @application.post("/ui/chat/completions", include_in_schema=False)
        async def ui_chat_completions(
            payload: ChatCompletionRequest,
            request: Request,
            engine: Literal["llama_cpp", "mlx_lm", "kserve_vllm"],
            _: str = Depends(authorize_and_limit),
        ) -> Any:
            _validate_request(payload, settings)
            return await proxy_completion(payload, request, application.state.ui_upstreams[engine])

    @application.post("/v1/chat/completions")
    async def chat_completions(
        payload: ChatCompletionRequest,
        request: Request,
        _: str = Depends(authorize_and_limit),
    ) -> Any:
        _validate_request(payload, settings)
        return await proxy_completion(payload, request, application.state.upstream)

    return application


app = create_app()
