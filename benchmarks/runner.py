from __future__ import annotations

import argparse
import asyncio
import json
import os
import platform
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import yaml

from benchmarks.schema import BenchmarkRun, RequestResult


@dataclass(frozen=True)
class RequestCase:
    prompt_id: str
    payload: dict[str, Any]


@dataclass(frozen=True)
class GpuSample:
    power_w: float
    memory_used_mib: float
    utilization_pct: float


class NvidiaSmiSampler:
    """Collect GPU telemetry with one long-lived nvidia-smi process."""

    def __init__(self, interval_ms: int = 500) -> None:
        self.interval_ms = interval_ms
        self.samples: list[GpuSample] = []
        self._process: subprocess.Popen[str] | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        command = [
            "nvidia-smi",
            "--query-gpu=power.draw,memory.used,utilization.gpu",
            "--format=csv,noheader,nounits",
            f"--loop-ms={self.interval_ms}",
        ]
        try:
            self._process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                bufsize=1,
            )
        except (FileNotFoundError, subprocess.SubprocessError):
            return
        self._thread = threading.Thread(target=self._collect, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self._process is None:
            return
        self._process.terminate()
        try:
            self._process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            self._process.kill()
            self._process.wait(timeout=2)
        if self._thread is not None:
            self._thread.join(timeout=2)

    def _collect(self) -> None:
        if self._process is None or self._process.stdout is None:
            return
        for line in self._process.stdout:
            values = [value.strip() for value in line.split(",")]
            if len(values) != 3:
                continue
            try:
                self.samples.append(GpuSample(*(float(value) for value in values)))
            except ValueError:
                continue

    def summary(self) -> dict[str, float | int | None]:
        if not self.samples:
            return {
                "gpu_samples": 0,
                "gpu_power_w_mean": None,
                "gpu_memory_used_mib_peak": None,
                "gpu_utilization_pct_mean": None,
            }
        return {
            "gpu_samples": len(self.samples),
            "gpu_power_w_mean": sum(sample.power_w for sample in self.samples) / len(self.samples),
            "gpu_memory_used_mib_peak": max(sample.memory_used_mib for sample in self.samples),
            "gpu_utilization_pct_mean": sum(sample.utilization_pct for sample in self.samples)
            / len(self.samples),
        }


class TruncatedStreamError(RuntimeError):
    pass


class UpstreamStreamError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def load_workload(path: Path, model_override: str | None = None) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        workload = yaml.safe_load(handle)
    if workload.get("schema_version") != 1:
        raise ValueError("unsupported workload schema_version")
    if not workload.get("prompts"):
        raise ValueError("workload must contain prompts")
    if model_override:
        workload.setdefault("defaults", {})["model"] = model_override
    return workload


def expand_cases(workload: dict[str, Any]) -> list[RequestCase]:
    defaults = dict(workload.get("defaults", {}))
    rounds = int(workload.get("execution", {}).get("rounds", 1))
    cases: list[RequestCase] = []
    for round_index in range(rounds):
        for prompt in workload["prompts"]:
            payload = dict(defaults)
            payload.update(prompt.get("parameters", {}))
            payload["messages"] = prompt["messages"]
            cases.append(
                RequestCase(
                    prompt_id=f"{prompt['id']}:r{round_index + 1}",
                    payload=payload,
                )
            )
    return cases


async def run_case(
    client: httpx.AsyncClient,
    url: str,
    case: RequestCase,
    headers: dict[str, str],
) -> RequestResult:
    request_id = uuid.uuid4().hex
    started = time.perf_counter()
    ttft_ms: float | None = None
    status_code: int | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None

    try:
        if case.payload.get("stream", False):
            saw_done = False
            async with client.stream(
                "POST",
                url,
                json=case.payload,
                headers={**headers, "X-Request-ID": request_id},
            ) as response:
                status_code = response.status_code
                if response.status_code != 200:
                    await response.aread()
                    raise RuntimeError(f"http_{response.status_code}")
                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if not data:
                        continue
                    if data == "[DONE]":
                        saw_done = True
                        continue
                    chunk = json.loads(data)
                    if "error" in chunk:
                        raise UpstreamStreamError("upstream_stream_error")
                    usage = chunk.get("usage") or {}
                    prompt_tokens = usage.get("prompt_tokens", prompt_tokens)
                    completion_tokens = usage.get("completion_tokens", completion_tokens)
                    for choice in chunk.get("choices", []):
                        delta = choice.get("delta") or {}
                        if delta.get("content") or delta.get("reasoning_content"):
                            if ttft_ms is None:
                                ttft_ms = (time.perf_counter() - started) * 1000
            if not saw_done:
                raise TruncatedStreamError("truncated_stream")
        else:
            response = await client.post(
                url,
                json=case.payload,
                headers={**headers, "X-Request-ID": request_id},
            )
            status_code = response.status_code
            if response.status_code != 200:
                raise RuntimeError(f"http_{response.status_code}")
            body = response.json()
            usage = body.get("usage") or {}
            prompt_tokens = usage.get("prompt_tokens")
            completion_tokens = usage.get("completion_tokens")

        e2e_ms = (time.perf_counter() - started) * 1000
        return RequestResult(
            request_id=request_id,
            prompt_id=case.prompt_id,
            success=True,
            status_code=status_code,
            ttft_ms=ttft_ms,
            e2e_ms=e2e_ms,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )
    except Exception as exc:
        return RequestResult(
            request_id=request_id,
            prompt_id=case.prompt_id,
            success=False,
            status_code=status_code,
            ttft_ms=ttft_ms,
            e2e_ms=(time.perf_counter() - started) * 1000,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            error=_safe_error(exc),
        )


def _safe_error(exc: Exception) -> str:
    """응답 본문이나 prompt가 결과 파일로 새지 않게 오류 종류만 남긴다."""

    message = str(exc)
    if message.startswith("http_"):
        return message
    if isinstance(exc, TruncatedStreamError):
        return "truncated_stream"
    if isinstance(exc, UpstreamStreamError):
        return "upstream_stream_error"
    if isinstance(exc, httpx.TimeoutException):
        return "timeout"
    if isinstance(exc, httpx.HTTPError):
        return type(exc).__name__
    if isinstance(exc, json.JSONDecodeError):
        return "invalid_json"
    return type(exc).__name__


async def execute(
    *,
    endpoint: str,
    workload: dict[str, Any],
    api_key: str | None,
    gpu_sampler: NvidiaSmiSampler | None = None,
) -> tuple[list[RequestResult], float]:
    execution = workload.get("execution", {})
    timeout = float(execution.get("timeout_seconds", 90))
    concurrency = max(1, int(execution.get("concurrency", 1)))
    warmup = max(0, int(execution.get("warmup_requests", 0)))
    cases = expand_cases(workload)
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    limits = httpx.Limits(
        max_connections=concurrency,
        max_keepalive_connections=concurrency,
    )
    async with httpx.AsyncClient(timeout=timeout, limits=limits) as client:
        for case in cases[:warmup]:
            await run_case(client, endpoint, case, headers)

        semaphore = asyncio.Semaphore(concurrency)

        async def bounded(case: RequestCase) -> RequestResult:
            async with semaphore:
                return await run_case(client, endpoint, case, headers)

        if gpu_sampler is not None:
            gpu_sampler.start()
        measurement_started = time.perf_counter()
        try:
            results = await asyncio.gather(*(bounded(case) for case in cases))
        finally:
            duration_seconds = time.perf_counter() - measurement_started
            if gpu_sampler is not None:
                gpu_sampler.stop()
        return results, duration_seconds


def collect_environment(labels: list[str]) -> dict[str, Any]:
    environment: dict[str, Any] = {
        "python": platform.python_version(),
        "platform": platform.platform(),
    }
    for name in ("RUN_IMAGE_DIGEST", "CUDA_VERSION", "NVIDIA_VISIBLE_DEVICES"):
        if value := os.getenv(name):
            environment[name.lower()] = value
    environment.update(_gpu_environment())
    for label in labels:
        key, separator, value = label.partition("=")
        if not separator or not key:
            raise ValueError(f"invalid label: {label!r}; expected KEY=VALUE")
        environment[key] = value
    return environment


def _gpu_environment() -> dict[str, Any]:
    command = [
        "nvidia-smi",
        "--query-gpu=name,driver_version,memory.total",
        "--format=csv,noheader,nounits",
    ]
    try:
        result = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (FileNotFoundError, subprocess.SubprocessError):
        return {"gpu": None}
    return {"gpu": [line.strip() for line in result.stdout.splitlines() if line.strip()]}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="OpenAI 호환 엔드포인트 벤치마크")
    parser.add_argument("--endpoint", required=True, help=".../v1/chat/completions URL")
    parser.add_argument("--workload", required=True, type=Path)
    parser.add_argument("--engine", required=True)
    parser.add_argument("--model")
    parser.add_argument("--model-revision", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--api-key-env", default="OPENAI_API_KEY")
    parser.add_argument("--label", action="append", default=[])
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    workload = load_workload(args.workload, args.model)
    model = workload.get("defaults", {}).get("model")
    if not model:
        raise ValueError("model must be set in workload defaults or --model")

    started_at = utc_now()
    gpu_sampler = NvidiaSmiSampler()
    results, duration_seconds = asyncio.run(
        execute(
            endpoint=args.endpoint,
            workload=workload,
            api_key=os.getenv(args.api_key_env),
            gpu_sampler=gpu_sampler,
        )
    )
    environment = collect_environment(args.label)
    environment["benchmark_duration_seconds"] = duration_seconds
    environment.update(gpu_sampler.summary())
    run = BenchmarkRun(
        schema_version=1,
        run_id=uuid.uuid4().hex,
        engine=args.engine,
        endpoint=args.endpoint,
        model=model,
        model_revision=args.model_revision,
        workload=workload["name"],
        started_at=started_at,
        finished_at=utc_now(),
        environment=environment,
        results=results,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(run.to_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    failures = sum(not result.success for result in results)
    print(f"wrote {len(results)} requests ({failures} failed) to {args.output}")
    return 0 if failures == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
