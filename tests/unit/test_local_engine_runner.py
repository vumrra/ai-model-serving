from pathlib import Path

import pytest


def _manifest(tmp_path: Path) -> Path:
    manifest = tmp_path / "manifest.yaml"
    manifest.write_text(
        """
models:
  llama_cpp:
    repo_id: ggml-org/Qwen3-0.6B-GGUF
    revision: b5f37287796e5be0ea3dab2e7430873fb3f73e49
    filename: Qwen3-0.6B-Q4_0.gguf
    model_alias: qwen3-0.6b
  mlx_lm:
    repo_id: mlx-community/Qwen3-0.6B-4bit
    revision: 73e3e38d981303bc594367cd910ea6eb48349da8
    model_alias: qwen3-0.6b
""",
        encoding="utf-8",
    )
    return manifest


def test_llama_command_downloads_pinned_gguf_and_uses_native_server(tmp_path: Path) -> None:
    from scripts.run_local_engine import resolve_engine_command

    downloads: list[tuple[str, str, str]] = []

    def download(repo_id: str, filename: str, revision: str) -> str:
        downloads.append((repo_id, filename, revision))
        return "/cache/Qwen3-0.6B-Q4_0.gguf"

    command = resolve_engine_command(
        "llama_cpp",
        _manifest(tmp_path),
        port=8003,
        which=lambda name: "/opt/homebrew/bin/llama-server" if name == "llama-server" else None,
        download_file=download,
    )

    assert downloads == [
        (
            "ggml-org/Qwen3-0.6B-GGUF",
            "Qwen3-0.6B-Q4_0.gguf",
            "b5f37287796e5be0ea3dab2e7430873fb3f73e49",
        )
    ]
    assert command == [
        "/opt/homebrew/bin/llama-server",
        "-m",
        "/cache/Qwen3-0.6B-Q4_0.gguf",
        "--alias",
        "qwen3-0.6b",
        "--host",
        "127.0.0.1",
        "--port",
        "8003",
    ]


def test_llama_command_supports_current_llama_cli_name(tmp_path: Path) -> None:
    from scripts.run_local_engine import resolve_engine_command

    command = resolve_engine_command(
        "llama_cpp",
        _manifest(tmp_path),
        port=8003,
        which=lambda name: "/opt/homebrew/bin/llama" if name == "llama" else None,
        download_file=lambda repo_id, filename, revision: "/cache/model.gguf",
    )

    assert command[:2] == ["/opt/homebrew/bin/llama", "serve"]


def test_mlx_command_downloads_pinned_snapshot_and_uses_native_server(tmp_path: Path) -> None:
    from scripts.run_local_engine import resolve_engine_command

    downloads: list[tuple[str, str]] = []

    def download(repo_id: str, revision: str) -> str:
        downloads.append((repo_id, revision))
        return "/cache/mlx-qwen"

    command = resolve_engine_command(
        "mlx_lm",
        _manifest(tmp_path),
        port=8004,
        python_executable="/venv/bin/python",
        download_snapshot=download,
    )

    assert downloads == [
        (
            "mlx-community/Qwen3-0.6B-4bit",
            "73e3e38d981303bc594367cd910ea6eb48349da8",
        )
    ]
    assert command == [
        "/venv/bin/python",
        "-m",
        "mlx_lm.server",
        "--model",
        "/cache/mlx-qwen",
        "--host",
        "127.0.0.1",
        "--port",
        "8004",
        "--chat-template-args",
        '{"enable_thinking": true}',
    ]


def test_runner_rejects_mutable_model_revision(tmp_path: Path) -> None:
    from scripts.run_local_engine import resolve_engine_command

    manifest = _manifest(tmp_path)
    manifest.write_text(
        manifest.read_text().replace("b5f37287796e5be0ea3dab2e7430873fb3f73e49", "main")
    )

    with pytest.raises(RuntimeError, match="immutable 40-character commit SHA"):
        resolve_engine_command(
            "llama_cpp",
            manifest,
            port=8003,
            which=lambda name: "/usr/local/bin/llama-server",
            download_file=lambda repo_id, filename, revision: "/cache/model.gguf",
        )
