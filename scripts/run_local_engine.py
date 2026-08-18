from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import yaml

_COMMIT_SHA = re.compile(r"^[0-9a-f]{40}$")


def resolve_engine_command(
    engine: str,
    manifest_path: Path,
    *,
    port: int,
    which: Callable[[str], str | None] | None = None,
    download_file: Callable[[str, str, str], str] | None = None,
    download_snapshot: Callable[[str, str], str] | None = None,
    python_executable: str | None = None,
) -> list[str]:
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    model: dict[str, Any] = manifest["models"][engine]
    repo_id = str(model["repo_id"])
    revision = str(model["revision"])
    alias = str(model["model_alias"])
    if not _COMMIT_SHA.fullmatch(revision):
        raise RuntimeError("model revision must be an immutable 40-character commit SHA")

    if engine == "llama_cpp":
        if download_file is None:
            from huggingface_hub import hf_hub_download

            def pinned_file(repo: str, filename: str, commit: str) -> str:
                return hf_hub_download(repo_id=repo, filename=filename, revision=commit)

            file_loader = pinned_file
        else:
            file_loader = download_file
        model_path = file_loader(repo_id, str(model["filename"]), revision)
        find = which or shutil.which
        legacy_binary = find("llama-server")
        if legacy_binary:
            command = [legacy_binary]
        else:
            current_binary = find("llama")
            if not current_binary:
                raise RuntimeError("llama.cpp is not installed; run: brew install llama.cpp")
            command = [current_binary, "serve"]
        return command + [
            "-m",
            model_path,
            "--alias",
            alias,
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ]

    if engine == "mlx_lm":
        if download_snapshot is None:
            from huggingface_hub import snapshot_download

            def pinned_snapshot(repo: str, commit: str) -> str:
                return snapshot_download(repo_id=repo, revision=commit)

            snapshot_loader = pinned_snapshot
        else:
            snapshot_loader = download_snapshot
        model_path = snapshot_loader(repo_id, revision)
        return [
            python_executable or sys.executable,
            "-m",
            "mlx_lm.server",
            "--model",
            model_path,
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--chat-template-args",
            json.dumps({"enable_thinking": False}),
        ]

    raise ValueError(f"unsupported engine: {engine}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="고정된 Qwen 로컬 추론 엔진을 실행합니다.")
    parser.add_argument("engine", choices=["llama_cpp", "mlx_lm"])
    parser.add_argument("--manifest", type=Path, default=Path("models/manifest.yaml"))
    parser.add_argument("--port", type=int)
    args = parser.parse_args()
    selected_port = args.port or (8003 if args.engine == "llama_cpp" else 8004)
    resolved = resolve_engine_command(args.engine, args.manifest, port=selected_port)
    os.execv(resolved[0], resolved)
