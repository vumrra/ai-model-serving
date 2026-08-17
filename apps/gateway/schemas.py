from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ChatMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["system", "user", "assistant"]
    content: str = Field(min_length=1, max_length=32_000)


class ChatCompletionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model: str = Field(min_length=1, max_length=200)
    messages: list[ChatMessage] = Field(min_length=1)
    stream: bool = False
    max_tokens: int = Field(default=256, ge=1, le=32_768)
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    top_p: float = Field(default=0.8, gt=0.0, le=1.0)
    seed: int | None = None


class HealthResponse(BaseModel):
    status: Literal["ok", "ready"]


class VersionResponse(BaseModel):
    service: str
    version: str
    release_id: str
    git_sha: str
    engine: str
    model: str
    model_revision: str
    gateway_image: str
    runtime_image: str
    serving_config_sha256: str
