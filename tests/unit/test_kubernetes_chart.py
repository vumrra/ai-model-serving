from __future__ import annotations

import os
import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).parents[2]
CHART = ROOT / "charts/qwen-serving"


def render(values: str) -> list[dict[str, object]]:
    result = subprocess.run(
        ["helm", "template", "qwen", str(CHART), "-f", str(CHART / values)],
        check=True,
        capture_output=True,
        text=True,
    )
    return [document for document in yaml.safe_load_all(result.stdout) if document]


def test_local_mlx_chart_uses_standard_kserve_without_gpu() -> None:
    documents = render("values-local-mlx-cpu.yaml")
    runtime = next(item for item in documents if item["kind"] == "ServingRuntime")
    service = next(item for item in documents if item["kind"] == "InferenceService")

    container = runtime["spec"]["containers"][0]  # type: ignore[index]
    assert container["image"] == "qwen-mlx-cpu:local"
    assert container["resources"]["requests"] == {"cpu": "2", "memory": "4Gi"}
    assert "nvidia.com/gpu" not in container["resources"]["limits"]
    assert container["readinessProbe"]["httpGet"]["port"] == 8000
    assert service["metadata"]["annotations"]["serving.kserve.io/deploymentMode"] == "Standard"
    assert service["spec"]["predictor"]["deploymentStrategy"]["type"] == "Recreate"
    assert service["spec"]["predictor"]["model"]["runtime"] == "qwen-mlx-cpu"
    assert service["spec"]["predictor"]["model"]["modelFormat"]["name"] == "huggingface"


def test_local_vllm_chart_uses_pinned_arm64_cpu_image() -> None:
    documents = render("values-local-vllm-cpu.yaml")
    runtime = next(item for item in documents if item["kind"] == "ServingRuntime")
    service = next(item for item in documents if item["kind"] == "InferenceService")
    cache = next(item for item in documents if item["kind"] == "PersistentVolumeClaim")

    container = runtime["spec"]["containers"][0]  # type: ignore[index]
    assert container["image"].startswith("docker.io/vllm/vllm-openai-cpu:v0.27.1-arm64@sha256:")
    assert container["args"][:3] == [
        "Qwen/Qwen3-1.7B",
        "--revision",
        "70d244cc86ccca08cf5af4e1e306ecf908b1ad5e",
    ]
    assert "bfloat16" in container["args"]
    assert container["resources"]["requests"] == {"cpu": "2", "memory": "6Gi"}
    assert container["resources"]["limits"] == {"cpu": "4", "memory": "10Gi"}
    assert "nvidia.com/gpu" not in container["resources"]["limits"]
    assert container["volumeMounts"] == [
        {"name": "dshm", "mountPath": "/dev/shm"},
        {"name": "model-cache", "mountPath": "/root/.cache/huggingface"},
    ]
    assert runtime["spec"]["volumes"] == [
        {"name": "dshm", "emptyDir": {"medium": "Memory", "sizeLimit": "1Gi"}},
        {
            "name": "model-cache",
            "persistentVolumeClaim": {"claimName": "qwen-vllm-cpu-model-cache"},
        },
    ]
    assert container["startupProbe"]["failureThreshold"] == 540
    assert cache["spec"]["storageClassName"] == "standard"
    assert cache["spec"]["resources"]["requests"]["storage"] == "12Gi"
    assert service["metadata"]["annotations"]["serving.kserve.io/deploymentMode"] == "Standard"
    assert service["spec"]["predictor"]["deploymentStrategy"]["type"] == "Recreate"
    assert service["spec"]["predictor"]["model"]["runtime"] == "qwen-vllm-cpu"


def test_mlx_entrypoint_rejects_mutable_revision_before_download() -> None:
    environment = os.environ | {"MODEL_ID": "mlx-community/Qwen3-4B-4bit", "MODEL_REVISION": "main"}
    result = subprocess.run(
        ["bash", str(ROOT / "engines/mlx_cpu/entrypoint.sh")],
        env=environment,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 64
    assert "immutable 40-character" in result.stderr


def test_local_kserve_disables_ingress_and_waits_for_service_readiness() -> None:
    kserve_values = yaml.safe_load(
        (ROOT / "deploy/kubernetes/kserve-values.yaml").read_text(encoding="utf-8")
    )
    gateway = kserve_values["kserve"]["controller"]["gateway"]
    assert gateway["disableIngressCreation"] is True

    taskfile = yaml.safe_load((ROOT / "Taskfile.yml").read_text(encoding="utf-8"))
    commands = taskfile["tasks"]["kserve-deploy"]["cmds"]
    assert any(
        "wait --for=condition=Ready inferenceservice/qwen-vllm-cpu" in command
        and "--timeout=60m" in command
        for command in commands
    )
    assert any(
        "rollout status deployment/qwen-vllm-cpu-predictor" in command for command in commands
    )


def test_open_webui_uses_gateway_and_persistent_volume() -> None:
    compose = yaml.safe_load(
        (ROOT / "deploy/local/compose.open-webui.yaml").read_text(encoding="utf-8")
    )
    service = compose["services"]["open-webui"]

    assert service["image"].startswith("ghcr.io/open-webui/open-webui:v0.11.0@sha256:")
    assert service["ports"] == ["3000:8080"]
    assert service["environment"]["OPENAI_API_BASE_URL"] == ("http://host.docker.internal:8000/v1")
    assert service["environment"]["OPENAI_API_KEY"] == ("${PUBLIC_API_KEY:-local-public-key}")
    assert service["environment"]["WEBUI_AUTH"] == "False"
    assert service["volumes"] == ["qwen-open-webui-data:/app/backend/data"]
