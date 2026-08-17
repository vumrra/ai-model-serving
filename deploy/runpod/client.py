from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen


class RunPodApiError(RuntimeError):
    """RunPod API가 성공 응답을 반환하지 않았을 때 발생합니다."""


@dataclass(slots=True)
class RunPodClient:
    api_key: str
    base_url: str = "https://rest.runpod.io/v1"

    def request(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
    ) -> dict[str, Any] | list[dict[str, Any]] | None:
        payload = json.dumps(body).encode() if body is not None else None
        request = Request(
            f"{self.base_url}{path}",
            data=payload,
            method=method,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
        )

        try:
            with urlopen(request, timeout=30) as response:  # noqa: S310
                if response.status == 204:
                    return None
                return json.loads(response.read())
        except HTTPError as error:
            detail = error.read().decode(errors="replace")
            raise RunPodApiError(f"RunPod API {error.code}: {detail}") from error

    def create_pod(self, payload: dict[str, Any]) -> dict[str, Any]:
        result = self.request("POST", "/pods", payload)
        if not isinstance(result, dict):
            raise RunPodApiError("Pod 생성 응답 형식이 올바르지 않습니다.")
        return result

    def list_pods(self) -> list[dict[str, Any]]:
        result = self.request("GET", "/pods")
        if not isinstance(result, list):
            raise RunPodApiError("Pod 목록 응답 형식이 올바르지 않습니다.")
        return result

    def delete_pod(self, pod_id: str) -> None:
        self.request("DELETE", f"/pods/{pod_id}")
