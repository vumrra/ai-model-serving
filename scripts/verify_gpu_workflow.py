from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

EXPECTED_WORKFLOWS = {"ci.yaml", "gpu-runtime.yaml", "cleanup-runpod.yaml"}


def load_workflow(path: Path) -> dict[str, Any]:
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise ValueError(f"invalid workflow: {path}")
    if True in document and "on" not in document:
        document["on"] = document.pop(True)
    return document


def validate_gpu_workflow(workflow: dict[str, Any]) -> None:
    errors: list[str] = []
    dispatch = workflow.get("on", {}).get("workflow_dispatch", {})
    inputs = dispatch.get("inputs", {})
    if inputs.get("engine", {}).get("options") != ["vllm", "sglang"]:
        errors.append("engine input must offer only vllm and sglang")
    for name in ("base_image", "engine_version"):
        if inputs.get(name, {}).get("required") is not True:
            errors.append(f"{name} input must be required")

    if workflow.get("permissions", {}).get("packages") != "write":
        errors.append("packages write permission is required")

    runtime = workflow.get("jobs", {}).get("runtime", {})
    environment = runtime.get("env", {})
    expected_environment = {
        "MODEL_ID": "Qwen/Qwen3-4B",
        "MODEL_REVISION": "1cfa9a7208912126459214e8b04321603b3df60c",
        "MODEL_DTYPE": "bfloat16",
        "MAX_MODEL_LEN": "8192",
        "TENSOR_PARALLEL_SIZE": "1",
        "GPU_MEMORY_UTILIZATION": "0.90",
    }
    for name, expected in expected_environment.items():
        if environment.get(name) != expected:
            errors.append(f"runtime env {name} must be {expected}")

    steps = runtime.get("steps", [])
    build = next((step for step in steps if step.get("id") == "runtime-image"), {})
    build_options = build.get("with", {})
    if build.get("uses") != "docker/build-push-action@v6":
        errors.append("runtime image must use docker/build-push-action@v6")
    if build_options.get("push") is not True:
        errors.append("runtime image must be pushed")
    if build_options.get("file") != "engines/${{ inputs.engine }}/Dockerfile":
        errors.append("runtime image must select the engine Dockerfile")
    if "${{ steps.metadata.outputs.repository }}" not in str(build_options.get("tags", "")):
        errors.append("runtime image must use the engine-specific repository")

    commands = "\n".join(str(step.get("run", "")) for step in steps)
    required_commands = {
        "create_pod.py": "RunPod creation",
        "steps.runtime-image.outputs.digest": "immutable runtime digest",
        "wait_ready.py": "readiness check",
        "benchmarks/workloads/smoke.yaml": "smoke workload",
    }
    for needle, label in required_commands.items():
        if needle not in commands:
            errors.append(f"workflow is missing {label}")

    upload = next(
        (step for step in steps if step.get("uses") == "actions/upload-artifact@v4"),
        {},
    )
    if upload.get("if") != "always()":
        errors.append("smoke artifact upload must run always")

    cleanup = next((step for step in steps if step.get("name") == "Always terminate Pod"), {})
    if cleanup.get("if") != "always()" or "delete_pod.py" not in str(cleanup.get("run", "")):
        errors.append("workflow must guarantee cleanup with always()")

    if errors:
        raise ValueError("; ".join(errors))


def verify_repository(root: Path = Path(".")) -> None:
    workflows = root / ".github/workflows"
    names = {path.name for path in workflows.glob("*.yaml")}
    if names != EXPECTED_WORKFLOWS:
        raise ValueError(
            f"workflow set must be {sorted(EXPECTED_WORKFLOWS)}, found {sorted(names)}"
        )
    validate_gpu_workflow(load_workflow(workflows / "gpu-runtime.yaml"))


def main() -> int:
    verify_repository()
    print("GPU workflow verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
