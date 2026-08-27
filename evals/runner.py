from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any

import httpx
import yaml


def load_cases(path: Path) -> list[dict[str, Any]]:
    suite = yaml.safe_load(path.read_text(encoding="utf-8"))
    if suite.get("schema_version") != 1 or not suite.get("cases"):
        raise ValueError("평가 suite 형식이 올바르지 않습니다.")
    return suite["cases"]


def grade(case: dict[str, Any], answer: str) -> list[str]:
    failures: list[str] = []
    required = case.get("required_any", [])
    if required and not any(word in answer for word in required):
        failures.append("required_keyword_missing")
    if any(word not in answer for word in case.get("required_all", [])):
        failures.append("required_keywords_missing")
    if expected := case.get("exact"):
        if answer.strip() != expected:
            failures.append("exact_answer_mismatch")
    if keys := case.get("json_keys"):
        try:
            document = json.loads(answer)
        except json.JSONDecodeError:
            failures.append("invalid_json")
        else:
            if not isinstance(document, dict) or any(key not in document for key in keys):
                failures.append("json_keys_missing")
    if any(word in answer for word in case.get("prohibited", [])):
        failures.append("prohibited_text_found")
    if len(answer) > int(case.get("max_chars", 2_000)):
        failures.append("answer_too_long")
    if not answer.strip():
        failures.append("empty_answer")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description="공개 API의 작은 품질 회귀 suite를 실행합니다.")
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--suite", type=Path, default=Path("evals/cases.yaml"))
    parser.add_argument("--model", default="qwen3-4b")
    parser.add_argument("--api-key-env", default="PUBLIC_API_KEY")
    parser.add_argument("--disable-thinking", action="store_true")
    parser.add_argument("--max-tokens", type=int, default=256)
    parser.add_argument("--output", type=Path, default=Path("evals/results/latest.json"))
    args = parser.parse_args()

    headers = {}
    if api_key := os.getenv(args.api_key_env):
        headers["Authorization"] = f"Bearer {api_key}"
    results = []
    with httpx.Client(headers=headers, timeout=90) as client:
        for case in load_cases(args.suite):
            payload = {
                "model": args.model,
                "messages": case["messages"],
                "temperature": 0,
                "max_tokens": args.max_tokens,
            }
            if args.disable_thinking:
                payload["chat_template_kwargs"] = {"enable_thinking": False}
            response = client.post(
                f"{args.base_url.rstrip('/')}/v1/chat/completions",
                json=payload,
            )
            response.raise_for_status()
            answer = response.json()["choices"][0]["message"]["content"]
            failures = grade(case, answer)
            results.append(
                {
                    "id": case["id"],
                    "passed": not failures,
                    "failures": failures,
                    "answer_sha256": hashlib.sha256(answer.encode()).hexdigest(),
                }
            )

    report = {
        "model": args.model,
        "thinking": not args.disable_thinking,
        "passed": all(item["passed"] for item in results),
        "score": sum(item["passed"] for item in results) / len(results),
        "results": results,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"quality eval: {sum(item['passed'] for item in results)}/{len(results)} passed")
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
