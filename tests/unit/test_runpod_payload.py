from argparse import Namespace

import pytest

from deploy.runpod.create_pod import build_payload, sanitize_pod


def test_runpod_payload_matches_engine_port(monkeypatch):
    monkeypatch.setenv("MODEL_ID", "Qwen/Qwen3-4B")
    monkeypatch.setenv("MODEL_REVISION", "a" * 40)
    monkeypatch.setenv("MODEL_DTYPE", "bfloat16")
    monkeypatch.setenv("MAX_MODEL_LEN", "8192")
    monkeypatch.setenv("TENSOR_PARALLEL_SIZE", "1")
    monkeypatch.setenv("GPU_MEMORY_UTILIZATION", "0.9")
    monkeypatch.setenv("RUNPOD_ENGINE_SECRET_NAME", "engine_key")
    monkeypatch.setenv("RUNPOD_REGISTRY_AUTH_ID", "registry-auth-id")
    args = Namespace(
        image="registry/runtime@sha256:" + "b" * 64,
        release_id="release-1",
        gpu="NVIDIA L40S",
        ttl_minutes=45,
        purpose="benchmark",
    )

    payload = build_payload(args)

    assert payload["ports"] == ["8000/http"]
    assert payload["gpuTypeIds"] == ["NVIDIA L40S"]
    assert payload["gpuCount"] == 1
    assert payload["env"]["MODEL_REVISION"] == "a" * 40
    assert payload["env"]["MODEL_ID"] == "Qwen/Qwen3-4B"
    assert payload["env"]["DTYPE"] == "bfloat16"
    assert payload["env"]["MAX_MODEL_LEN"] == "8192"
    assert payload["env"]["TENSOR_PARALLEL_SIZE"] == "1"
    assert payload["env"]["GPU_MEMORY_UTILIZATION"] == "0.9"
    assert payload["env"]["ENGINE_API_KEY"] == "{{ RUNPOD_SECRET_engine_key }}"
    assert payload["containerRegistryAuthId"] == "registry-auth-id"
    assert payload["name"].startswith("qwen-serving-lab-benchmark-release-1-exp")

    summary = sanitize_pod(
        {"id": "pod-1", "costPerHr": "0.99", "env": {"ENGINE_API_KEY": "secret"}},
        payload,
    )
    assert summary["proxyUrl"] == "https://pod-1-8000.proxy.runpod.net"
    assert "env" not in summary
    assert "secret" not in str(summary)


@pytest.mark.parametrize(
    "image",
    [
        "ghcr.io/acme/qwen-vllm:latest",
        "ghcr.io/acme/qwen-vllm@sha256:short",
        "ghcr.io/acme/qwen-vllm@sha256:" + "A" * 64,
    ],
)
def test_runpod_payload_rejects_mutable_or_malformed_runtime_image(
    monkeypatch: pytest.MonkeyPatch,
    image: str,
) -> None:
    monkeypatch.setenv("MODEL_ID", "Qwen/Qwen3-4B")
    monkeypatch.setenv("MODEL_REVISION", "a" * 40)
    monkeypatch.setenv("MODEL_DTYPE", "bfloat16")
    monkeypatch.setenv("MAX_MODEL_LEN", "8192")
    monkeypatch.setenv("TENSOR_PARALLEL_SIZE", "1")
    monkeypatch.setenv("GPU_MEMORY_UTILIZATION", "0.9")
    args = Namespace(
        image=image,
        release_id="release-1",
        gpu="NVIDIA L40S",
        ttl_minutes=45,
        purpose="benchmark",
    )

    with pytest.raises(ValueError, match="image.*digest"):
        build_payload(args)
