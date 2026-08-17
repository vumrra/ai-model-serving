from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class RequestResult:
    request_id: str
    prompt_id: str
    success: bool
    status_code: int | None
    ttft_ms: float | None
    e2e_ms: float
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    error: str | None = None

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> RequestResult:
        return cls(**value)


@dataclass(frozen=True)
class BenchmarkRun:
    schema_version: int
    run_id: str
    engine: str
    endpoint: str
    model: str
    model_revision: str
    workload: str
    started_at: str
    finished_at: str
    environment: dict[str, Any]
    results: list[RequestResult] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> BenchmarkRun:
        data = dict(value)
        data["results"] = [RequestResult.from_dict(item) for item in data["results"]]
        return cls(**data)
