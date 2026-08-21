from __future__ import annotations

import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).parents[2]
STACK = Path(__file__).parent
CHART = ROOT / "charts/qwen-serving"


def render() -> list[dict[str, object]]:
    result = subprocess.run(
        ["helm", "template", "qwen", str(CHART), "-f", str(STACK / "values.yaml")],
        check=True,
        capture_output=True,
        text=True,
    )
    return [document for document in yaml.safe_load_all(result.stdout) if document]


def test_wsl2_gpu_contract() -> None:
    documents = render()
    runtime = next(item for item in documents if item["kind"] == "ServingRuntime")
    service = next(item for item in documents if item["kind"] == "InferenceService")
    cache = next(item for item in documents if item["kind"] == "PersistentVolumeClaim")
    container = runtime["spec"]["containers"][0]  # type: ignore[index]

    assert container["image"] == (
        "docker.io/vllm/vllm-openai:v0.8.5@sha256:"
        "6cf9808ca8810fc6c3fd0451c2e7784fb224590d81f7db338e7eaf3c02a33d33"
    )
    assert container["args"] == [
        "Qwen/Qwen3-1.7B",
        "--revision",
        "70d244cc86ccca08cf5af4e1e306ecf908b1ad5e",
        "--dtype",
        "float16",
        "--max-model-len",
        "1024",
        "--max-num-seqs",
        "1",
        "--gpu-memory-utilization",
        "0.85",
        "--served-model-name",
        "qwen3-1.7b",
    ]
    assert container["resources"]["requests"]["nvidia.com/gpu"] == 1
    assert container["resources"]["limits"]["nvidia.com/gpu"] == 1
    assert container["volumeMounts"] == [
        {"name": "dshm", "mountPath": "/dev/shm"},
        {"name": "model-cache", "mountPath": "/root/.cache"},
    ]
    assert service["metadata"]["annotations"]["serving.kserve.io/deploymentMode"] == ("Standard")
    assert service["spec"]["predictor"]["deploymentStrategy"]["type"] == "Recreate"
    assert service["spec"]["predictor"]["minReplicas"] == 1
    assert service["spec"]["predictor"]["maxReplicas"] == 1
    assert cache["spec"]["resources"]["requests"]["storage"] == "16Gi"


def test_wsl2_tasks_keep_endpoints_local_and_cluster_deletion_explicit() -> None:
    taskfile = yaml.safe_load((STACK / "Taskfile.yml").read_text(encoding="utf-8"))
    tasks = taskfile["tasks"]

    assert "--gpus=all" in tasks["minikube-up"]["cmds"][0]
    assert "--address 127.0.0.1" in tasks["kserve-forward"]["cmds"][0]
    assert "minikube delete" not in (STACK / "Taskfile.yml").read_text(encoding="utf-8")

    smoke = yaml.safe_load((STACK / "gpu-smoke.yaml").read_text(encoding="utf-8"))
    container = smoke["spec"]["containers"][0]
    assert container["image"] == (
        "docker.io/library/ubuntu@sha256:"
        "2260313b31c8c011cd2eebe728008efac1b3982be73eb71348ea2648d2c0e09b"
    )
    assert container["resources"]["limits"] == {"nvidia.com/gpu": 1}
