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
