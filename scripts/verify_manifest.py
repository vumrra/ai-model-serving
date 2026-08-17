from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

_IMAGE_DIGEST = re.compile(r"^.+@sha256:[0-9a-f]{64}$")
_COMMIT_SHA = re.compile(r"^[0-9a-f]{40}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def verify_release(release: dict[str, object]) -> None:
    if release.get("schema_version") != "1.0":
        raise ValueError("지원하지 않는 release schema입니다.")
    for image_key in ("gateway_image", "runtime_image"):
        if not _IMAGE_DIGEST.fullmatch(str(release.get(image_key, ""))):
            raise ValueError(f"{image_key}는 정확한 sha256 digest여야 합니다.")

    model = release.get("model")
    if not isinstance(model, dict) or not _COMMIT_SHA.fullmatch(str(model.get("revision", ""))):
        raise ValueError("model revision은 40자리 lowercase commit SHA여야 합니다.")
    if not _SHA256.fullmatch(str(release.get("serving_config_sha256", ""))):
        raise ValueError("serving config SHA-256 형식이 올바르지 않습니다.")
    engine = release.get("engine")
    if not isinstance(engine, dict) or engine.get("name") not in {"vllm", "sglang"}:
        raise ValueError("engine 이름이 올바르지 않습니다.")
    serving = release.get("serving")
    if not isinstance(serving, dict):
        raise ValueError("serving 실행 설정이 없습니다.")
    if int(serving.get("max_model_len", 0)) <= 0:
        raise ValueError("max_model_len이 올바르지 않습니다.")
    utilization = float(serving.get("gpu_memory_utilization", 0))
    if not 0 < utilization <= 1:
        raise ValueError("gpu_memory_utilization이 올바르지 않습니다.")


def main() -> int:
    parser = argparse.ArgumentParser(description="release의 필수 고정값을 검사합니다.")
    parser.add_argument("manifest", type=Path)
    args = parser.parse_args()

    release = json.loads(args.manifest.read_text(encoding="utf-8"))
    verify_release(release)
    print("release manifest verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
