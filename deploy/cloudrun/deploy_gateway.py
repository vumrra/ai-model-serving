from __future__ import annotations

import argparse
import subprocess


def main() -> int:
    parser = argparse.ArgumentParser(description="Cloud Run Gateway revision을 배포합니다.")
    parser.add_argument("--service", required=True)
    parser.add_argument("--region", default="asia-northeast3")
    parser.add_argument("--image", required=True, help="Artifact Registry image digest")
    parser.add_argument("--engine-url", required=True)
    parser.add_argument("--release-id", required=True)
    parser.add_argument("--service-account", required=True)
    parser.add_argument("--engine-model-name", required=True)
    parser.add_argument("--model-revision", required=True)
    parser.add_argument("--runtime-image", required=True)
    parser.add_argument("--serving-config-sha256", required=True)
    parser.add_argument("--model-alias", default="qwen3-4b")
    parser.add_argument("--engine-name", choices=["vllm", "sglang"], default="vllm")
    parser.add_argument("--rate-limit-requests", type=int, default=30)
    parser.add_argument("--public-key-secret", default="qwen-public-api-key")
    parser.add_argument("--engine-key-secret", default="qwen-engine-api-key")
    parser.add_argument("--no-traffic", action="store_true")
    parser.add_argument("--tag", help="검증용 Cloud Run revision tag")
    args = parser.parse_args()

    command = [
        "gcloud",
        "run",
        "deploy",
        args.service,
        "--region",
        args.region,
        "--image",
        args.image,
        "--allow-unauthenticated",
        "--service-account",
        args.service_account,
        "--min-instances",
        "0",
        "--max-instances",
        "1",
        "--concurrency",
        "32",
        "--timeout",
        "95s",
        "--set-env-vars",
        (
            f"ENGINE_BASE_URL={args.engine_url},RELEASE_ID={args.release_id},"
            f"ENGINE_MODEL_NAME={args.engine_model_name},MODEL_ALIAS={args.model_alias},"
            f"ENGINE_NAME={args.engine_name},MODEL_REVISION={args.model_revision},"
            f"GATEWAY_IMAGE={args.image},RUNTIME_IMAGE={args.runtime_image},"
            f"SERVING_CONFIG_SHA256={args.serving_config_sha256},"
            f"RATE_LIMIT_REQUESTS={args.rate_limit_requests}"
        ),
        "--set-secrets",
        (
            f"PUBLIC_API_KEY={args.public_key_secret}:latest,"
            f"ENGINE_API_KEY={args.engine_key_secret}:latest"
        ),
    ]
    if args.no_traffic:
        command.append("--no-traffic")
    if args.tag:
        command.extend(["--tag", args.tag])

    # shell=False가 기본이므로 입력값이 셸 명령으로 실행되지 않습니다.
    subprocess.run(command, check=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
