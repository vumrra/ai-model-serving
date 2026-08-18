from copy import deepcopy
from pathlib import Path

import pytest

from scripts.verify_gpu_workflow import load_workflow, validate_gpu_workflow, verify_repository

ROOT = Path(__file__).parents[2]


def test_repository_has_one_safe_gpu_runtime_workflow() -> None:
    verify_repository(ROOT)


def test_verifier_rejects_workflow_without_guaranteed_cleanup() -> None:
    workflow = load_workflow(ROOT / ".github/workflows/gpu-runtime.yaml")
    unsafe = deepcopy(workflow)
    unsafe["jobs"]["runtime"]["steps"] = [
        step
        for step in unsafe["jobs"]["runtime"]["steps"]
        if step.get("name") != "Always terminate Pod"
    ]

    with pytest.raises(ValueError, match="cleanup"):
        validate_gpu_workflow(unsafe)
