import json
from collections import Counter
from pathlib import Path

from evals.runner import build_report, grade, load_cases, main, wilson_95


def test_grade_reports_quality_failures():
    case = {
        "required_any": ["42"],
        "prohibited": ["secret"],
        "max_chars": 10,
    }

    assert grade(case, "secret answer") == [
        "required_keyword_missing",
        "prohibited_text_found",
        "answer_too_long",
    ]


def test_grade_accepts_matching_answer():
    assert grade({"required_any": ["42"], "max_chars": 10}, "42") == []


def test_grade_supports_exact_required_all_and_json():
    assert grade({"exact": "42"}, "42") == []
    assert grade({"exact": "42"}, "42입니다") == ["exact_answer_mismatch"]
    assert grade({"required_all": ["Pod", "Service"]}, "Pod only") == ["required_keywords_missing"]
    assert grade({"json_keys": ["service", "ready"]}, '{"service":"qwen","ready":true}') == []
    assert grade({"json_keys": ["service"]}, "not-json") == ["invalid_json"]


def test_grade_supports_json_equals():
    expected = {"ready": True, "count": 2, "tags": ["gpu", "fp16"]}
    assert grade({"json_equals": expected}, '{"ready":true,"count":2,"tags":["gpu","fp16"]}') == []
    assert (
        grade(
            {"json_equals": expected},
            '{"tags":["gpu","fp16"],"count":2,"ready":true}',
        )
        == []
    )
    assert grade({"json_equals": expected}, '{"ready":false}') == ["json_value_mismatch"]
    assert grade({"json_equals": {"ready": True}}, '{"ready":1}') == ["json_value_mismatch"]
    assert grade({"json_equals": expected}, "not-json") == ["invalid_json"]


def test_wilson_95_handles_empty_and_known_sample():
    assert wilson_95(0, 0) == {"lower": 0.0, "upper": 0.0}
    assert wilson_95(5, 10) == {"lower": 0.236593, "upper": 0.763407}


def test_build_report_groups_categories_and_intervals():
    results = [
        {"category": "instruction", "passed": True},
        {"category": "instruction", "passed": False},
        {"category": "safety", "passed": True},
    ]
    report = build_report("qwen", False, results)

    assert report["passed"] is False
    assert report["passed_count"] == 2
    assert report["total"] == 3
    assert report["score"] == 2 / 3
    assert report["wilson_95"] == wilson_95(2, 3)
    assert report["categories"]["instruction"] == {
        "passed": 1,
        "total": 2,
        "score": 0.5,
        "wilson_95": wilson_95(1, 2),
    }
    assert report["categories"]["safety"]["score"] == 1.0


def test_main_allow_failures_preserves_hash_only(tmp_path, monkeypatch):
    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {"choices": [{"message": {"content": "raw answer"}}]}

    class Client:
        def __init__(self, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            pass

        def post(self, *_args, **_kwargs):
            return Response()

    suite = tmp_path / "suite.yaml"
    suite.write_text(
        """schema_version: 1
cases:
  - id: failing
    category: instruction
    messages:
      - role: user
        content: say 42
    exact: "42"
""",
        encoding="utf-8",
    )
    output = tmp_path / "result.json"
    monkeypatch.setattr("evals.runner.httpx.Client", Client)
    args = [
        "--base-url",
        "http://example.test",
        "--suite",
        str(suite),
        "--output",
        str(output),
    ]

    assert main(args) == 2
    assert main([*args, "--allow-failures"]) == 0

    text = output.read_text(encoding="utf-8")
    report = json.loads(text)
    result = report["results"][0]
    assert report["passed"] is False
    assert result["category"] == "instruction"
    assert set(result) == {
        "id",
        "category",
        "passed",
        "failures",
        "answer_sha256",
    }
    assert "raw answer" not in text


def test_chat_quality_suite_has_30_balanced_unique_cases():
    cases = load_cases(Path("stacks/wsl2-gpu/evals/chat-quality.yaml"))
    categories = Counter(case["category"] for case in cases)

    assert len(cases) == 30
    assert len({case["id"] for case in cases}) == 30
    assert categories == {
        "arithmetic": 5,
        "code_structure": 4,
        "domain_explanation": 4,
        "json_values": 5,
        "korean_instruction": 4,
        "multi_turn_context": 4,
        "security_abstention": 4,
    }
