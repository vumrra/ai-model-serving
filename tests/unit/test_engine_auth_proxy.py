import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient

from engines.auth_proxy import create_app


def test_proxy_allows_only_authenticated_inference_routes(monkeypatch):
    monkeypatch.setenv("ENGINE_API_KEY", "engine-key")
    engine = FastAPI()

    @engine.get("/v1/models")
    async def models():
        return {"data": [{"id": "qwen"}]}

    proxy = create_app("http://engine", httpx.ASGITransport(app=engine), "engine-key")
    with TestClient(proxy) as client:
        unauthorized = client.get("/v1/models")
        allowed = client.get("/v1/models", headers={"Authorization": "Bearer engine-key"})
        blocked = client.post("/abort_requests", headers={"Authorization": "Bearer engine-key"})

    assert unauthorized.status_code == 401
    assert allowed.status_code == 200
    assert blocked.status_code == 404
