from __future__ import annotations

import hmac
import os
from collections.abc import AsyncIterator

import httpx
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import Response, StreamingResponse
from starlette.background import BackgroundTask


def create_app(
    engine_url: str = "http://127.0.0.1:8001",
    transport: httpx.AsyncBaseTransport | None = None,
    api_key: str | None = None,
) -> FastAPI:
    app = FastAPI(title="qwen-engine-auth-proxy", docs_url=None, redoc_url=None)
    resolved_api_key = api_key or os.getenv("ENGINE_API_KEY", "")

    def authorize(authorization: str | None) -> None:
        scheme, _, token = (authorization or "").partition(" ")
        if (
            not resolved_api_key
            or scheme.lower() != "bearer"
            or not token
            or not hmac.compare_digest(token, resolved_api_key)
        ):
            raise HTTPException(status_code=401, detail="invalid engine API key")

    async def forward(request: Request, path: str) -> Response:
        body = await request.body()
        if len(body) > 131_072:
            raise HTTPException(status_code=413, detail="engine request body too large")
        client = httpx.AsyncClient(base_url=engine_url, transport=transport, timeout=90)
        upstream = client.build_request(
            request.method,
            path,
            content=body or None,
            headers={
                "Authorization": f"Bearer {resolved_api_key}",
                "Content-Type": request.headers.get("Content-Type", "application/json"),
                "X-Request-ID": request.headers.get("X-Request-ID", "engine-proxy"),
            },
        )
        try:
            response = await client.send(upstream, stream=True)
        except Exception:
            await client.aclose()
            raise

        async def chunks() -> AsyncIterator[bytes]:
            async for chunk in response.aiter_raw():
                yield chunk

        async def close() -> None:
            await response.aclose()
            await client.aclose()

        return StreamingResponse(
            chunks(),
            status_code=response.status_code,
            media_type=response.headers.get("Content-Type"),
            background=BackgroundTask(close),
        )

    @app.get("/livez")
    async def livez() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/v1/models")
    async def models(
        request: Request,
        authorization: str | None = Header(default=None),
    ) -> Response:
        authorize(authorization)
        return await forward(request, "/v1/models")

    @app.post("/v1/chat/completions")
    async def chat(
        request: Request,
        authorization: str | None = Header(default=None),
    ) -> Response:
        authorize(authorization)
        return await forward(request, "/v1/chat/completions")

    return app


app = create_app()
