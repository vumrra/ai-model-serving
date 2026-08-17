from __future__ import annotations

import json
import time
from collections.abc import AsyncIterator
from contextlib import AbstractAsyncContextManager
from typing import Any

import httpx
from fastapi import Request

from apps.gateway.config import Settings
from apps.gateway.errors import GatewayError
from apps.gateway.metrics import GatewayMetrics


def _headers(settings: Settings, request_id: str) -> dict[str, str]:
    headers = {"X-Request-ID": request_id}
    if settings.upstream_api_key:
        headers["Authorization"] = f"Bearer {settings.upstream_api_key}"
    return headers


def _upstream_message(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except (json.JSONDecodeError, ValueError):
        return "Inference engine returned an invalid error response."
    error = payload.get("error") if isinstance(payload, dict) else None
    if isinstance(error, dict) and isinstance(error.get("message"), str):
        return error["message"]
    return "Inference engine rejected the request."


def _transport_error(exc: httpx.HTTPError) -> GatewayError:
    if isinstance(exc, httpx.TimeoutException):
        return GatewayError(
            504,
            "upstream_timeout",
            "Inference engine timed out.",
            "upstream_timeout",
        )
    return GatewayError(
        502,
        "upstream_unavailable",
        "Inference engine is unavailable.",
        "upstream_error",
    )


class UpstreamClient:
    def __init__(
        self,
        settings: Settings,
        transport: httpx.AsyncBaseTransport | None = None,
        metrics: GatewayMetrics | None = None,
    ) -> None:
        self.settings = settings
        self.transport = transport
        self.metrics = metrics

    def _client(self, timeout: float | None = None) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self.settings.upstream_base_url,
            timeout=timeout or self.settings.upstream_timeout_seconds,
            transport=self.transport,
        )

    async def complete(self, payload: dict[str, Any], request_id: str) -> dict[str, Any]:
        try:
            async with self._client() as client:
                response = await client.post(
                    "/v1/chat/completions",
                    json=payload,
                    headers=_headers(self.settings, request_id),
                )
        except httpx.HTTPError as exc:
            raise _transport_error(exc) from exc

        if response.status_code >= 400:
            raise GatewayError(
                502,
                "upstream_rejected",
                _upstream_message(response),
                "upstream_error",
            )
        try:
            result = response.json()
        except (json.JSONDecodeError, ValueError) as exc:
            raise GatewayError(
                502,
                "invalid_upstream_response",
                "Inference engine returned invalid JSON.",
                "upstream_error",
            ) from exc
        if not isinstance(result, dict):
            raise GatewayError(
                502,
                "invalid_upstream_response",
                "Inference engine returned invalid JSON.",
                "upstream_error",
            )
        return result

    async def stream(
        self,
        payload: dict[str, Any],
        request_id: str,
        request: Request,
    ) -> AsyncIterator[bytes]:
        client = self._client()
        started = time.perf_counter()
        stream_context: AbstractAsyncContextManager[httpx.Response] = client.stream(
            "POST",
            "/v1/chat/completions",
            json=payload,
            headers=_headers(self.settings, request_id),
        )
        try:
            response = await stream_context.__aenter__()
        except httpx.HTTPError as exc:
            await client.aclose()
            raise _transport_error(exc) from exc

        if response.status_code >= 400:
            await response.aread()
            message = _upstream_message(response)
            await stream_context.__aexit__(None, None, None)
            await client.aclose()
            raise GatewayError(
                502,
                "upstream_rejected",
                message,
                "upstream_error",
            )

        async def iterator() -> AsyncIterator[bytes]:
            ttft_recorded = False
            try:
                async for line in response.aiter_lines():
                    if await request.is_disconnected():
                        break
                    if line.startswith("data:"):
                        data = line.removeprefix("data:").strip()
                        if data and data != "[DONE]":
                            try:
                                event = json.loads(data)
                            except json.JSONDecodeError:
                                event = None
                            if isinstance(event, dict) and "model" in event:
                                event["model"] = self.settings.public_model_name
                                line = f"data: {json.dumps(event, ensure_ascii=False)}"
                            if isinstance(event, dict) and not ttft_recorded:
                                choices = event.get("choices", [])
                                if any(
                                    choice.get("delta", {}).get("content") for choice in choices
                                ):
                                    if self.metrics:
                                        self.metrics.ttft.observe(time.perf_counter() - started)
                                    ttft_recorded = True
                    yield f"{line}\n".encode()
            except httpx.HTTPError:
                if self.metrics:
                    self.metrics.stream_errors.inc()
                error = {
                    "error": {
                        "message": "Inference stream was interrupted.",
                        "type": "upstream_error",
                        "code": "stream_interrupted",
                        "request_id": request_id,
                    }
                }
                yield b"event: error\n"
                yield f"data: {json.dumps(error)}\n\n".encode()
            finally:
                await stream_context.__aexit__(None, None, None)
                await client.aclose()

        return iterator()

    async def is_ready(self) -> bool:
        try:
            async with self._client(self.settings.readiness_timeout_seconds) as client:
                response = await client.get(
                    "/v1/models",
                    headers=_headers(self.settings, "readiness-probe"),
                )
        except httpx.HTTPError:
            return False
        return response.status_code == 200
