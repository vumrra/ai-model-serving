from __future__ import annotations

import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).parents[2]
STACK = Path(__file__).parent
CHART = ROOT / "charts/qwen-serving"
GATEWAY_CHART = STACK / "gateway"
GITOPS_CHART = STACK / "gitops"


def render() -> list[dict[str, object]]:
    result = subprocess.run(
        ["helm", "template", "qwen", str(CHART), "-f", str(STACK / "values.yaml")],
        check=True,
        capture_output=True,
        text=True,
    )
    return [document for document in yaml.safe_load_all(result.stdout) if document]


def render_gateway() -> list[dict[str, object]]:
    result = subprocess.run(
        ["helm", "template", "gateway", str(GATEWAY_CHART), "--set-string", "image.tag=testsha"],
        check=True,
        capture_output=True,
        text=True,
    )
    return [document for document in yaml.safe_load_all(result.stdout) if document]


def render_gitops() -> list[dict[str, object]]:
    result = subprocess.run(
        [
            "helm",
            "template",
            "gitops",
            str(GITOPS_CHART),
            "--set-string",
            "repoRevision=codex/windows-gpu",
            "--set",
            "gateway.enabled=true",
        ],
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
        "--model",
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
        "--swap-space",
        "0",
        "--served-model-name",
        "qwen3-1.7b",
    ]
    assert container["resources"]["requests"]["nvidia.com/gpu"] == 1
    assert container["resources"]["limits"]["nvidia.com/gpu"] == 1
    assert {item["name"]: item["value"] for item in container["env"]}["HF_HUB_DISABLE_XET"] == "1"
    assert container["volumeMounts"] == [
        {"name": "dshm", "mountPath": "/dev/shm"},
        {"name": "model-cache", "mountPath": "/root/.cache"},
        {
            "name": "wsl2-dxcore",
            "mountPath": "/usr/lib/x86_64-linux-gnu/libdxcore.so",
            "readOnly": True,
        },
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
    assert "--address 127.0.0.1" in tasks["gateway-forward"]["cmds"][0]
    assert "minikube delete" not in (STACK / "Taskfile.yml").read_text(encoding="utf-8")

    smoke = yaml.safe_load((STACK / "gpu-smoke.yaml").read_text(encoding="utf-8"))
    container = smoke["spec"]["containers"][0]
    assert container["image"] == (
        "docker.io/library/ubuntu@sha256:"
        "2260313b31c8c011cd2eebe728008efac1b3982be73eb71348ea2648d2c0e09b"
    )
    assert container["resources"]["limits"] == {"nvidia.com/gpu": 1}


def test_gateway_is_api_only_and_uses_a_secret() -> None:
    documents = render_gateway()
    deployment = next(item for item in documents if item["kind"] == "Deployment")
    service = next(item for item in documents if item["kind"] == "Service")
    container = deployment["spec"]["template"]["spec"]["containers"][0]  # type: ignore[index]
    environment = {item["name"]: item for item in container["env"]}

    assert container["image"] == "qwen-gateway:testsha"
    assert environment["PUBLIC_API_KEY"]["valueFrom"]["secretKeyRef"] == {
        "name": "qwen-gateway-api-key",
        "key": "api-key",
    }
    assert environment["ENGINE_BASE_URL"]["value"] == (
        "http://qwen-vllm-gpu-predictor.qwen-serving.svc.cluster.local"
    )
    assert environment["MODEL_ALIAS"]["value"] == "qwen-demo"
    assert environment["ENGINE_MODEL_NAME"]["value"] == "qwen3-1.7b"
    assert environment["ENABLE_THINKING"]["value"] == "false"
    assert environment["CHAT_UI_ENABLED"]["value"] == "false"
    assert environment["RUNTIME_IMAGE"]["value"].endswith(
        "@sha256:6cf9808ca8810fc6c3fd0451c2e7784fb224590d81f7db338e7eaf3c02a33d33"
    )
    assert service["spec"]["type"] == "ClusterIP"
    assert not any(item["kind"] == "Ingress" for item in documents)


def test_gateway_accepts_an_immutable_image_digest() -> None:
    result = subprocess.run(
        [
            "helm",
            "template",
            "gateway",
            str(GATEWAY_CHART),
            "--set-string",
            "image.digest=sha256:testdigest",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    documents = [document for document in yaml.safe_load_all(result.stdout) if document]
    deployment = next(item for item in documents if item["kind"] == "Deployment")
    container = deployment["spec"]["template"]["spec"]["containers"][0]  # type: ignore[index]

    assert container["image"] == "qwen-gateway@sha256:testdigest"


def test_gitops_apps_pull_git_without_cluster_credentials_in_ci() -> None:
    documents = render_gitops()
    applications = [item for item in documents if item["kind"] == "Application"]

    assert {item["metadata"]["name"] for item in applications} == {
        "qwen-cert-manager",
        "qwen-kserve-crd",
        "qwen-kserve",
        "qwen-model",
        "qwen-gateway",
    }
    assert all(item["spec"]["syncPolicy"]["automated"]["selfHeal"] for item in applications)
    assert not any(item["kind"] == "Secret" for item in documents)
    model = next(item for item in applications if item["metadata"]["name"] == "qwen-model")
    assert model["spec"]["sources"][0]["targetRevision"] == "codex/windows-gpu"

    workflow = (ROOT / ".github/workflows/wsl2-gpu-release.yml").read_text(encoding="utf-8")
    assert "platforms: linux/amd64" in workflow
    assert "steps.build.outputs.digest" in workflow
    assert "values-gitops.yaml" in workflow
    assert "kubectl" not in workflow
    assert "KUBECONFIG" not in workflow


def test_post_sync_smoke_uses_the_gateway_digest_and_secret() -> None:
    result = subprocess.run(
        [
            "helm",
            "template",
            "gateway",
            str(GATEWAY_CHART),
            "--values",
            str(GATEWAY_CHART / "values-gitops.yaml"),
            "--set-string",
            "image.digest=sha256:testdigest",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    documents = [document for document in yaml.safe_load_all(result.stdout) if document]
    job = next(item for item in documents if item["kind"] == "Job")
    container = job["spec"]["template"]["spec"]["containers"][0]

    assert job["metadata"]["annotations"]["argocd.argoproj.io/hook"] == "PostSync"
    assert container["image"] == "ghcr.io/vumrra/ai-model-serving/gateway@sha256:testdigest"
    assert container["env"][0]["valueFrom"]["secretKeyRef"]["name"] == ("qwen-gateway-api-key")
