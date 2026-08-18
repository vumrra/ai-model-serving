import os
from pathlib import Path

import pytest


def test_smoke_environment_comes_from_model_manifest(tmp_path: Path) -> None:
    from scripts.run_transformers_cpu import smoke_environment

    manifest = tmp_path / "manifest.yaml"
    manifest.write_text(
        """
models:
  smoke:
    repo_id: example/model
    revision: 0123456789abcdef0123456789abcdef01234567
    default_dtype: float32
""",
        encoding="utf-8",
    )

    assert smoke_environment(manifest) == {
        "MODEL_ID": "example/model",
        "MODEL_REVISION": "0123456789abcdef0123456789abcdef01234567",
        "MODEL_DEVICE": "cpu",
        "MODEL_DTYPE": "float32",
    }


def test_main_forces_manifest_cpu_settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from scripts.run_transformers_cpu import main

    models = tmp_path / "models"
    models.mkdir()
    (models / "manifest.yaml").write_text(
        """
models:
  smoke:
    repo_id: example/model
    revision: 0123456789abcdef0123456789abcdef01234567
    default_dtype: float32
""",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("MODEL_ID", "wrong/model")
    monkeypatch.setenv("MODEL_DEVICE", "mps")
    monkeypatch.setattr("scripts.run_transformers_cpu.uvicorn.run", lambda *args, **kwargs: None)

    main()

    assert os.environ["MODEL_ID"] == "example/model"
    assert os.environ["MODEL_REVISION"] == "0123456789abcdef0123456789abcdef01234567"
    assert os.environ["MODEL_DEVICE"] == "cpu"
    assert os.environ["MODEL_DTYPE"] == "float32"
