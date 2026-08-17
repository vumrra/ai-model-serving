from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

import yaml


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description="재현 가능한 release manifest를 만듭니다.")
    parser.add_argument("--gateway-image", required=True)
    parser.add_argument("--runtime-image", required=True)
    parser.add_argument("--engine", choices=["vllm", "sglang"], required=True)
    parser.add_argument("--engine-version", required=True)
    parser.add_argument(
        "--model-profile",
        choices=["smoke", "benchmark"],
        default="benchmark",
    )
    parser.add_argument("--dtype", required=True)
    parser.add_argument("--serving-config", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=Path("releases/generated"))
    args = parser.parse_args()

    model_manifest = yaml.safe_load(Path("models/manifest.yaml").read_text(encoding="utf-8"))
    model = model_manifest["models"][args.model_profile]
    serving_config = yaml.safe_load(args.serving_config.read_text(encoding="utf-8"))
    runtime_environment = serving_config["runtime"]["environment"]
    git_sha = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    release_id = f"{git_sha[:7]}-{args.engine}-{args.dtype}-{sha256(args.serving_config)[:7]}"

    manifest = {
        "schema_version": "1.0",
        "release_id": release_id,
        "git_sha": git_sha,
        "gateway_image": args.gateway_image,
        "runtime_image": args.runtime_image,
        "engine": {"name": args.engine, "version": args.engine_version},
        "model": {
            "id": model["repo_id"],
            "revision": model["revision"],
            "dtype": args.dtype,
        },
        "serving": {
            "max_model_len": int(runtime_environment["MAX_MODEL_LEN"]),
            "tensor_parallel_size": int(runtime_environment["TENSOR_PARALLEL_SIZE"]),
            "gpu_memory_utilization": float(runtime_environment["GPU_MEMORY_UTILIZATION"]),
            "chat_template_kwargs": model["chat_template_kwargs"],
        },
        "serving_config_sha256": sha256(args.serving_config),
    }

    args.output_dir.mkdir(parents=True, exist_ok=True)
    output = args.output_dir / f"{release_id}.json"
    output.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
