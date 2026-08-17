from __future__ import annotations

import argparse
import json
import os

import httpx


def request_payload(stream: bool) -> dict[str, object]:
    return {
        "model": os.getenv("SMOKE_MODEL", os.getenv("MODEL_ALIAS", "qwen3-4b")),
        "messages": [{"role": "user", "content": "한 문장으로 인사해 주세요."}],
        "max_tokens": 32,
        "temperature": 0,
        "stream": stream,
    }


def check_json(client: httpx.Client, endpoint: str) -> None:
    response = client.post(endpoint, json=request_payload(stream=False))
    response.raise_for_status()
    content = response.json()["choices"][0]["message"]["content"]
    if not isinstance(content, str) or not content.strip():
        raise RuntimeError("JSON 응답에 답변 문장이 없습니다.")


def check_stream(client: httpx.Client, endpoint: str) -> None:
    done = False
    content_seen = False
    with client.stream("POST", endpoint, json=request_payload(stream=True)) as response:
        response.raise_for_status()
        for line in response.iter_lines():
            if not line.startswith("data:"):
                continue
            data = line.removeprefix("data:").strip()
            if data == "[DONE]":
                done = True
                continue
            chunk = json.loads(data)
            if "error" in chunk:
                raise RuntimeError("SSE 도중 engine 오류가 반환됐습니다.")
            content_seen |= any(
                bool(choice.get("delta", {}).get("content")) for choice in chunk.get("choices", [])
            )
    if not done or not content_seen:
        raise RuntimeError("SSE 응답의 content 또는 [DONE]이 없습니다.")


def check_metrics(client: httpx.Client, base_url: str) -> None:
    response = client.get(f"{base_url.rstrip('/')}/metrics")
    response.raise_for_status()
    required = {
        "qwen_http_requests_total",
        "qwen_active_requests",
        "qwen_engine_ready",
        "qwen_stream_errors_total",
    }
    if not all(name in response.text for name in required):
        raise RuntimeError("필수 Gateway metric이 노출되지 않습니다.")


def check_health(client: httpx.Client, base_url: str) -> None:
    live = client.get(f"{base_url.rstrip('/')}/livez")
    ready = client.get(f"{base_url.rstrip('/')}/readyz")
    live.raise_for_status()
    ready.raise_for_status()


def main() -> int:
    parser = argparse.ArgumentParser(description="배포된 공개 API의 JSON과 SSE를 확인합니다.")
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--api-key-env", default="PUBLIC_API_KEY")
    parser.add_argument("--expected-release-id")
    parser.add_argument("--expected-model-revision")
    parser.add_argument("--expected-runtime-image")
    parser.add_argument("--expected-serving-config-sha256")
    args = parser.parse_args()

    api_key = os.environ[args.api_key_env]
    endpoint = f"{args.base_url.rstrip('/')}/v1/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}"}
    with httpx.Client(headers=headers, timeout=90) as client:
        check_health(client, args.base_url)
        if args.expected_release_id:
            version = client.get(f"{args.base_url.rstrip('/')}/version")
            version.raise_for_status()
            deployed = version.json()
            expected = {
                "release_id": args.expected_release_id,
                "model_revision": args.expected_model_revision,
                "runtime_image": args.expected_runtime_image,
                "serving_config_sha256": args.expected_serving_config_sha256,
            }
            for key, value in expected.items():
                if value and deployed.get(key) != value:
                    raise RuntimeError(f"배포된 {key}가 승인 manifest와 다릅니다.")
        check_json(client, endpoint)
        check_stream(client, endpoint)
        check_metrics(client, args.base_url)
    print("public API smoke passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
