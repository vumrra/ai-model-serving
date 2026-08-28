from __future__ import annotations

import subprocess
import sys
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
    annotations = service["metadata"]["annotations"]

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
        "0.75",
        "--enable-prefix-caching",
        "--swap-space",
        "0",
        "--served-model-name",
        "qwen3-1.7b",
    ]
    assert container["resources"]["requests"]["nvidia.com/gpu"] == "1"
    assert container["resources"]["limits"]["nvidia.com/gpu"] == "1"
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
    assert annotations["serving.kserve.io/deploymentMode"] == "Standard"
    assert annotations["serving.kserve.io/autoscalerClass"] == "none"
    assert "serving.kserve.io/autoscaler-class" not in annotations
    assert service["spec"]["predictor"]["deploymentStrategy"]["type"] == "Recreate"
    assert service["spec"]["predictor"]["minReplicas"] == 1
    assert service["spec"]["predictor"]["maxReplicas"] == 1
    assert cache["spec"]["resources"]["requests"]["storage"] == "16Gi"


def test_wsl2_tasks_keep_endpoints_local_and_cluster_deletion_explicit() -> None:
    taskfile_text = (STACK / "Taskfile.yml").read_text(encoding="utf-8")
    taskfile = yaml.safe_load(taskfile_text)
    tasks = taskfile["tasks"]

    assert "--gpus=all" in tasks["minikube-up"]["cmds"][0]
    assert "--address 127.0.0.1" in tasks["kserve-forward"]["cmds"][0]
    assert "--address 127.0.0.1" in tasks["gateway-forward"]["cmds"][0]
    assert "--address=127.0.0.1" in tasks["kubernetes-dashboard-forward"]["cmds"][0]
    assert "--port=8001" in tasks["kubernetes-dashboard-forward"]["cmds"][0]
    assert "--address 127.0.0.1" in tasks["argocd-forward"]["cmds"][0]
    assert "minikube delete" not in taskfile_text
    assert "s|targetRevision: main|targetRevision: {{.GIT_REVISION}}|" in taskfile_text
    benchmark = tasks["perf-benchmark"]["cmds"][0]
    assert "--engine vllm-v0-xformers-graph-prefix-cache" in benchmark
    assert "config_id=qwen3-1.7b-fp16-util075-seq1-graph-prefix-on" in benchmark
    assert "gpu_memory_utilization=0.75" in benchmark
    assert "enable_prefix_caching=true" in benchmark
    assert "${PERF_RUN_ID:-latest}" in benchmark
    soak = tasks["perf-soak"]["cmds"][0]
    assert "${PERF_BASE_URL:-http://127.0.0.1:8005}/v1/chat/completions" in soak
    assert "benchmarks/chat-single-raw.yaml" in soak
    assert "--engine vllm-v0-xformers-graph-prefix-cache" in soak
    assert "--model qwen3-1.7b" in soak
    assert "--model-revision 70d244cc86ccca08cf5af4e1e306ecf908b1ad5e" in soak
    assert "--concurrency 1" in soak
    assert "--rounds 72" in soak
    assert "study/qwen3-1.7b-fp16-util075-final-soak-c1.json" in soak
    assert "config_id=qwen3-1.7b-fp16-util075-seq1-graph-prefix-on" in soak
    assert "test_kind=final_soak" in soak
    assert "quantization=none" in soak
    assert "enforce_eager=false" in soak
    assert "gpu_memory_utilization=0.75" in soak
    assert "enable_prefix_caching=true" in soak
    assert "max_model_len=1024" in soak
    assert "max_num_seqs=1" in soak
    assert "thinking=false" in soak
    assert "slo_ttft_p95_ms=1000" in soak
    assert "slo_tpot_p95_ms=100" in soak
    assert "slo_gpu_peak_mib=5454" in soak
    assert "slo_gpu_free_min_mib=512" in soak
    assert "electricity_krw_per_kwh=200" in soak
    capacity = tasks["perf-capacity-4b"]
    capacity_command = capacity["cmds"][0]
    assert capacity["requires"]["vars"] == ["PERF_BASE_URL"]
    assert "--model qwen3-4b-awq" in capacity_command
    assert "--model-revision 74d4bd2bd4bff9cafc9345221320bffb08b406a3" in capacity_command
    assert "slo_gpu_peak_mib=5710" in capacity_command
    assert "slo_gpu_free_min_mib=256" in capacity_command
    quality = tasks["perf-quality"]
    quality_command = quality["cmds"][0]
    assert "30개" in quality["desc"]
    assert "--allow-failures" in quality_command
    assert "study/qwen3-1.7b-fp16-quality-30.json" in quality_command
    startup = " ".join(tasks["perf-startup"]["cmds"])
    assert "benchmarks.startup /dev/stdin" in startup
    assert "study/startup-qwen3-1.7b-util075-prefix-on.json" in startup
    assert "artifacts/performance/report.html" in tasks["perf-report"]["desc"]

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
    project = next(item for item in documents if item["kind"] == "AppProject")

    assert {item["metadata"]["name"] for item in applications} == {
        "qwen-cert-manager",
        "qwen-kserve-crd",
        "qwen-kserve",
        "qwen-model",
        "qwen-gateway",
    }
    assert all(item["spec"]["syncPolicy"]["automated"]["selfHeal"] for item in applications)
    assert not any(item["kind"] == "Secret" for item in documents)
    assert {(item["server"], item["namespace"]) for item in project["spec"]["destinations"]} >= {
        ("https://kubernetes.default.svc", "kube-system")
    }
    kserve = next(item for item in applications if item["metadata"]["name"] == "qwen-kserve")
    controller_values = kserve["spec"]["source"]["helm"]["valuesObject"]["kserve"]["controller"]
    assert kserve["spec"]["source"]["targetRevision"] == "v0.19.0"
    assert controller_values["resources"] == {"limits": {"cpu": "500m"}}
    manual_values = yaml.safe_load(
        (ROOT / "deploy/kubernetes/kserve-values.yaml").read_text(encoding="utf-8")
    )
    assert manual_values["kserve"]["controller"]["resources"] == controller_values["resources"]
    model = next(item for item in applications if item["metadata"]["name"] == "qwen-model")
    assert model["spec"]["sources"][0]["targetRevision"] == "codex/windows-gpu"
    assert model["spec"]["ignoreDifferences"] == [
        {
            "group": "serving.kserve.io",
            "kind": "InferenceService",
            "jsonPointers": ["/spec/predictor/model/name"],
        }
    ]

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


def test_performance_report_is_reproducible(tmp_path: Path) -> None:
    output = tmp_path / "report.html"
    subprocess.run(
        [
            sys.executable,
            str(STACK / "report.py"),
            "--artifacts",
            str(STACK / "artifacts/performance"),
            "--output",
            str(output),
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    report = output.read_text(encoding="utf-8")
    assert output.read_bytes() == (STACK / "artifacts/performance/report.html").read_bytes()
    assert "GTX 1660 LLM 서빙 실측 보고서" in report
    assert "시간당 출력 토큰" in report
    assert "원/백만 출력 토큰" in report
    assert "이전 Gateway E2E · util 0.80 단일 실행" in report
    assert "37,259" in report
    assert "265.1" in report
    assert "MLOps/sglang.md" in report
    assert "JaeoneLim/nano-kpu" in report
    assert "qwen3-1.7b" in report
    assert "qwen3-4b-awq" in report
    assert "4B 개별 요청 충족은 178/180" in report
    assert "보수 free 약 521MiB" in report
    assert (
        "최종 util 0.75 + prefix cache 구성의 Gateway E2E 비교는 아직 재측정하지 않았으므로"
        in report
    )
