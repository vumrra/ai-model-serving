from evals.runner import grade


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
