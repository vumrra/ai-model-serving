from __future__ import annotations

from urllib.error import URLError
from urllib.request import Request

import pytest

from deploy.runpod import wait_ready


class ReadyResponse:
    status = 200

    def __enter__(self) -> ReadyResponse:
        return self

    def __exit__(self, *args: object) -> None:
        return None


def test_readiness_retries_unavailable_engine_and_sends_bearer_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requests: list[Request] = []

    def open_engine(request: Request, timeout: float) -> ReadyResponse:
        requests.append(request)
        if len(requests) == 1:
            raise URLError("starting")
        return ReadyResponse()

    monkeypatch.setattr(wait_ready, "urlopen", open_engine)
    monkeypatch.setattr(wait_ready.time, "sleep", lambda seconds: None)

    wait_ready.wait_until_ready(
        "https://pod-1-8000.proxy.runpod.net/v1/models",
        "engine-key",
        timeout_seconds=1,
        poll_seconds=0.01,
    )

    assert len(requests) == 2
    assert requests[0].full_url.endswith("/v1/models")
    assert requests[0].get_header("Authorization") == "Bearer engine-key"


def test_readiness_times_out_when_engine_stays_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        wait_ready,
        "urlopen",
        lambda request, timeout: (_ for _ in ()).throw(URLError("starting")),
    )
    with pytest.raises(TimeoutError, match="engine.*ready"):
        wait_ready.wait_until_ready(
            "https://pod-1-8000.proxy.runpod.net/v1/models",
            "engine-key",
            timeout_seconds=0.02,
            poll_seconds=0.005,
        )
