from __future__ import annotations

import asyncio
import contextlib
import importlib
import json
import os
import queue
import threading
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, Protocol

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatCompletionRequest(BaseModel):
    """비교 실험에 필요한 OpenAI Chat Completions 요청의 최소 부분집합."""

    model_config = ConfigDict(extra="allow")

    model: str
    messages: list[ChatMessage] = Field(min_length=1)
    max_tokens: int = Field(default=128, ge=1, le=4096)
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    top_p: float = Field(default=1.0, gt=0.0, le=1.0)
    stream: bool = False
    chat_template_kwargs: dict[str, Any] = Field(default_factory=lambda: {"enable_thinking": False})


@dataclass(frozen=True)
class Generation:
    text: str
    prompt_tokens: int
    completion_tokens: int
    finish_reason: str


class InferenceBackend(Protocol):
    model_name: str

    async def generate(self, request: ChatCompletionRequest) -> Generation: ...

    def stream(self, request: ChatCompletionRequest) -> AsyncIterator[str]: ...

    def count_tokens(self, text: str) -> int: ...


class TransformersBackend:
    def __init__(
        self,
        *,
        model_id: str,
        revision: str,
        device: str = "auto",
        dtype: str = "auto",
    ) -> None:
        torch = importlib.import_module("torch")
        transformers = importlib.import_module("transformers")
        AutoModelForCausalLM = transformers.AutoModelForCausalLM
        AutoTokenizer = transformers.AutoTokenizer

        resolved_device = self._resolve_device(torch, device)
        resolved_dtype = self._resolve_dtype(torch, dtype, resolved_device)

        self.model_name = model_id
        self._torch = torch
        self._device = resolved_device
        self._tokenizer = AutoTokenizer.from_pretrained(
            model_id,
            revision=revision,
            trust_remote_code=False,
        )
        self._model = AutoModelForCausalLM.from_pretrained(
            model_id,
            revision=revision,
            torch_dtype=resolved_dtype,
            trust_remote_code=False,
            low_cpu_mem_usage=True,
        ).to(resolved_device)
        self._model.eval()

    @classmethod
    def from_env(cls) -> TransformersBackend:
        revision = os.environ.get("MODEL_REVISION")
        if not revision:
            raise RuntimeError("MODEL_REVISION must be an immutable Hugging Face commit SHA")
        return cls(
            model_id=os.getenv("MODEL_ID", "Qwen/Qwen3-0.6B"),
            revision=revision,
            device=os.getenv("MODEL_DEVICE", "auto"),
            dtype=os.getenv("MODEL_DTYPE", "auto"),
        )

    @staticmethod
    def _resolve_device(torch: Any, requested: str) -> str:
        if requested != "auto":
            return requested
        if torch.cuda.is_available():
            return "cuda"
        if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
            return "mps"
        return "cpu"

    @staticmethod
    def _resolve_dtype(torch: Any, requested: str, device: str) -> Any:
        if requested == "auto":
            return torch.bfloat16 if device == "cuda" else torch.float32
        choices = {
            "float32": torch.float32,
            "float16": torch.float16,
            "bfloat16": torch.bfloat16,
        }
        try:
            return choices[requested]
        except KeyError as exc:
            raise ValueError(f"unsupported MODEL_DTYPE: {requested}") from exc

    def _prepare(self, request: ChatCompletionRequest) -> tuple[dict[str, Any], int]:
        messages = [message.model_dump() for message in request.messages]
        template_kwargs = dict(request.chat_template_kwargs)
        try:
            encoded = self._tokenizer.apply_chat_template(
                messages,
                tokenize=True,
                add_generation_prompt=True,
                return_tensors="pt",
                return_dict=True,
                **template_kwargs,
            )
        except TypeError:
            # Qwen 외 tokenizer smoke에서도 최소 서버를 재사용할 수 있게 한다.
            encoded = self._tokenizer.apply_chat_template(
                messages,
                tokenize=True,
                add_generation_prompt=True,
                return_tensors="pt",
                return_dict=True,
            )
        inputs = {key: value.to(self._device) for key, value in encoded.items()}
        return inputs, int(inputs["input_ids"].shape[-1])

    def _generation_kwargs(self, request: ChatCompletionRequest) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "max_new_tokens": request.max_tokens,
            "do_sample": request.temperature > 0,
            "pad_token_id": self._tokenizer.pad_token_id,
            "eos_token_id": self._tokenizer.eos_token_id,
        }
        if request.temperature > 0:
            kwargs.update(temperature=request.temperature, top_p=request.top_p)
        return kwargs

    async def generate(self, request: ChatCompletionRequest) -> Generation:
        inputs, prompt_tokens = self._prepare(request)
        kwargs = self._generation_kwargs(request)

        def _run() -> Any:
            with self._torch.inference_mode():
                return self._model.generate(**inputs, **kwargs)

        outputs = await asyncio.to_thread(_run)
        generated_ids = outputs[0][prompt_tokens:]
        text = self._tokenizer.decode(generated_ids, skip_special_tokens=True)
        completion_tokens = int(generated_ids.shape[-1])
        return Generation(
            text=text,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            finish_reason="length" if completion_tokens >= request.max_tokens else "stop",
        )

    async def stream(self, request: ChatCompletionRequest) -> AsyncIterator[str]:
        transformers = importlib.import_module("transformers")
        StoppingCriteria = transformers.StoppingCriteria
        StoppingCriteriaList = transformers.StoppingCriteriaList
        TextIteratorStreamer = transformers.TextIteratorStreamer

        class EventStoppingCriteria(StoppingCriteria):
            def __init__(self, event: threading.Event) -> None:
                self._event = event

            def __call__(self, *args: Any, **kwargs: Any) -> bool:
                return self._event.is_set()

        inputs, _ = self._prepare(request)
        stop_event = threading.Event()
        stopping = EventStoppingCriteria(stop_event)
        streamer = TextIteratorStreamer(
            self._tokenizer,
            skip_prompt=True,
            skip_special_tokens=True,
            timeout=0.5,
        )
        kwargs = self._generation_kwargs(request)
        kwargs.update(streamer=streamer, stopping_criteria=StoppingCriteriaList([stopping]))

        def _run() -> Any:
            with self._torch.inference_mode():
                return self._model.generate(**inputs, **kwargs)

        task = asyncio.create_task(asyncio.to_thread(_run))
        iterator = iter(streamer)
        try:
            while True:
                state, item = await asyncio.to_thread(_next_stream_item, iterator)
                if state == "data":
                    if item:
                        yield item
                    continue
                if state == "empty" and not task.done():
                    continue
                if state == "done":
                    break
                await task
            await task
        finally:
            stop_event.set()
            if not task.done():
                task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task

    def count_tokens(self, text: str) -> int:
        return len(self._tokenizer.encode(text, add_special_tokens=False))


def _next_stream_item(iterator: Any) -> tuple[str, str | None]:
    try:
        return "data", next(iterator)
    except StopIteration:
        return "done", None
    except queue.Empty:
        return "empty", None


def create_app(backend: InferenceBackend | None = None) -> FastAPI:
    state: dict[str, InferenceBackend | None] = {"backend": backend}
    concurrency = max(1, int(os.getenv("MAX_CONCURRENT_REQUESTS", "1")))
    semaphore = asyncio.Semaphore(concurrency)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        if state["backend"] is None:
            state["backend"] = await asyncio.to_thread(TransformersBackend.from_env)
        yield

    service = FastAPI(title="Transformers OpenAI Baseline", lifespan=lifespan)

    def current_backend() -> InferenceBackend:
        active = state["backend"]
        if active is None:
            raise HTTPException(status_code=503, detail="model is not ready")
        return active

    @service.get("/livez")
    async def livez() -> dict[str, str]:
        return {"status": "ok"}

    @service.get("/readyz")
    async def readyz() -> dict[str, str]:
        active = current_backend()
        return {"status": "ready", "model": active.model_name}

    @service.get("/v1/models")
    async def models() -> dict[str, Any]:
        active = current_backend()
        return {"object": "list", "data": [{"id": active.model_name, "object": "model"}]}

    @service.post("/v1/chat/completions")
    async def chat_completions(request: ChatCompletionRequest) -> Any:
        active = current_backend()
        if request.stream:
            return StreamingResponse(
                _stream_response(active, request, semaphore),
                media_type="text/event-stream",
                headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
            )

        async with semaphore:
            started = int(time.time())
            completion = await active.generate(request)
        return {
            "id": f"chatcmpl-{uuid.uuid4().hex}",
            "object": "chat.completion",
            "created": started,
            "model": active.model_name,
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": completion.text},
                    "finish_reason": completion.finish_reason,
                }
            ],
            "usage": {
                "prompt_tokens": completion.prompt_tokens,
                "completion_tokens": completion.completion_tokens,
                "total_tokens": completion.prompt_tokens + completion.completion_tokens,
            },
        }

    return service


async def _stream_response(
    backend: InferenceBackend,
    request: ChatCompletionRequest,
    semaphore: asyncio.Semaphore,
) -> AsyncIterator[str]:
    completion_id = f"chatcmpl-{uuid.uuid4().hex}"
    created = int(time.time())

    def event(delta: dict[str, str], finish_reason: str | None = None) -> str:
        payload = {
            "id": completion_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": backend.model_name,
            "choices": [{"index": 0, "delta": delta, "finish_reason": finish_reason}],
        }
        return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"

    async with semaphore:
        yield event({"role": "assistant"})
        generated: list[str] = []
        async for text in backend.stream(request):
            generated.append(text)
            yield event({"content": text})
        finish_reason = (
            "length" if backend.count_tokens("".join(generated)) >= request.max_tokens else "stop"
        )
        yield event({}, finish_reason)
        yield "data: [DONE]\n\n"


app = create_app()
