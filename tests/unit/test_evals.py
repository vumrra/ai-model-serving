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
