from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from scripts.verify_manifest import verify_release


def release_environment(release: dict[str, object]) -> dict[str, str]:
    verify_release(release)
    engine = release["engine"]
    model = release["model"]
    serving = release["serving"]
    assert isinstance(engine, dict)
    assert isinstance(model, dict)
    assert isinstance(serving, dict)
    return {
        "RELEASE_ID": str(release["release_id"]),
        "GATEWAY_IMAGE": str(release["gateway_image"]),
        "RUNTIME_IMAGE": str(release["runtime_image"]),
        "ENGINE_NAME": str(engine["name"]),
        "ENGINE_VERSION": str(engine["version"]),
        "MODEL_ID": str(model["id"]),
        "MODEL_REVISION": str(model["revision"]),
        "MODEL_DTYPE": str(model["dtype"]),
        "MAX_MODEL_LEN": str(serving["max_model_len"]),
        "TENSOR_PARALLEL_SIZE": str(serving["tensor_parallel_size"]),
        "GPU_MEMORY_UTILIZATION": str(serving["gpu_memory_utilization"]),
        "SERVING_CONFIG_SHA256": str(release["serving_config_sha256"]),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="검증한 release를 GitHub Actions env로 냅니다.")
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    release = json.loads(args.manifest.read_text(encoding="utf-8"))
    destination = args.output or Path(os.environ["GITHUB_ENV"])
    lines = [f"{key}={value}" for key, value in release_environment(release).items()]
    with destination.open("a", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")
    print("release environment exported")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
