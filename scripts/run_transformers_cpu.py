from __future__ import annotations

import os
from pathlib import Path

import uvicorn
import yaml


def smoke_environment(manifest_path: Path) -> dict[str, str]:
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    model = manifest["models"]["smoke"]
    return {
        "MODEL_ID": str(model["repo_id"]),
        "MODEL_REVISION": str(model["revision"]),
        "MODEL_DEVICE": "cpu",
        "MODEL_DTYPE": str(model["default_dtype"]),
    }


def main() -> None:
    os.environ.update(smoke_environment(Path("models/manifest.yaml")))
    uvicorn.run(
        "engines.transformers.app:app",
        host="127.0.0.1",
        port=int(os.getenv("PORT", "8002")),
    )


if __name__ == "__main__":
    main()
