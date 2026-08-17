from __future__ import annotations

import os
from dataclasses import dataclass


def _env_int(name: str, default: int) -> int:
    value = int(os.getenv(name, str(default)))
    if value <= 0:
        raise ValueError(f"{name} must be greater than zero")
    return value


def _env_float(name: str, default: float) -> float:
    value = float(os.getenv(name, str(default)))
    if value <= 0:
        raise ValueError(f"{name} must be greater than zero")
    return value


def _env_alias(name: str, legacy_name: str, default: str) -> str:
    return os.getenv(name, os.getenv(legacy_name, default))


@dataclass(frozen=True, slots=True)
class Settings:
    service_name: str = "qwen-serving-gateway"
    service_version: str = "0.1.0"
    release_id: str = "local-dev"
    git_sha: str = "unknown"
    engine_name: str = "mock"
    model_revision: str = "unknown"
    gateway_image: str = "unknown"
    runtime_image: str = "unknown"
    serving_config_sha256: str = "unknown"
    public_model_name: str = "qwen-demo"
    upstream_model_name: str = "mock-qwen"
    upstream_base_url: str = "http://127.0.0.1:8001"
    api_key: str = "dev-secret"
    upstream_api_key: str = "mock-internal-key"
    upstream_timeout_seconds: float = 30.0
    readiness_timeout_seconds: float = 2.0
    max_body_bytes: int = 65_536
    max_messages: int = 20
    max_prompt_chars: int = 32_000
    max_completion_tokens: int = 512
    rate_limit_requests: int = 5
    rate_limit_window_seconds: int = 60

    @classmethod
    def from_env(cls) -> Settings:
        defaults = cls()
        return cls(
            service_name=os.getenv("SERVICE_NAME", defaults.service_name),
            service_version=os.getenv("SERVICE_VERSION", defaults.service_version),
            release_id=os.getenv("RELEASE_ID", defaults.release_id),
            git_sha=os.getenv("GIT_SHA", defaults.git_sha),
            engine_name=os.getenv("ENGINE_NAME", defaults.engine_name),
            model_revision=os.getenv("MODEL_REVISION", defaults.model_revision),
            gateway_image=os.getenv("GATEWAY_IMAGE", defaults.gateway_image),
            runtime_image=os.getenv("RUNTIME_IMAGE", defaults.runtime_image),
            serving_config_sha256=os.getenv(
                "SERVING_CONFIG_SHA256", defaults.serving_config_sha256
            ),
            public_model_name=_env_alias(
                "MODEL_ALIAS", "PUBLIC_MODEL_NAME", defaults.public_model_name
            ),
            upstream_model_name=_env_alias(
                "ENGINE_MODEL_NAME", "UPSTREAM_MODEL_NAME", defaults.upstream_model_name
            ),
            upstream_base_url=_env_alias(
                "ENGINE_BASE_URL", "UPSTREAM_BASE_URL", defaults.upstream_base_url
            ).rstrip("/"),
            api_key=_env_alias("PUBLIC_API_KEY", "GATEWAY_API_KEY", defaults.api_key),
            upstream_api_key=_env_alias(
                "ENGINE_API_KEY", "UPSTREAM_API_KEY", defaults.upstream_api_key
            ),
            upstream_timeout_seconds=_env_float(
                "UPSTREAM_TIMEOUT_SECONDS", defaults.upstream_timeout_seconds
            ),
            readiness_timeout_seconds=_env_float(
                "READINESS_TIMEOUT_SECONDS", defaults.readiness_timeout_seconds
            ),
            max_body_bytes=_env_int("MAX_BODY_BYTES", defaults.max_body_bytes),
            max_messages=_env_int("MAX_MESSAGES", defaults.max_messages),
            max_prompt_chars=_env_int("MAX_PROMPT_CHARS", defaults.max_prompt_chars),
            max_completion_tokens=_env_int("MAX_COMPLETION_TOKENS", defaults.max_completion_tokens),
            rate_limit_requests=_env_int("RATE_LIMIT_REQUESTS", defaults.rate_limit_requests),
            rate_limit_window_seconds=_env_int(
                "RATE_LIMIT_WINDOW_SECONDS", defaults.rate_limit_window_seconds
            ),
        )
