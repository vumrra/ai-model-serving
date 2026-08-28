from benchmarks.startup import summarize_pod


def test_summarize_pod_reports_startup_milestones() -> None:
    pod = {
        "metadata": {
            "name": "qwen-predictor-abc",
            "namespace": "qwen-serving",
            "creationTimestamp": "2026-08-28T01:00:00Z",
            "uid": "must-not-leak",
        },
        "status": {
            "phase": "Running",
            "conditions": [
                {
                    "type": "PodScheduled",
                    "lastTransitionTime": "2026-08-28T01:00:02Z",
                },
                {
                    "type": "ContainersReady",
                    "lastTransitionTime": "2026-08-28T01:00:42Z",
                },
                {
                    "type": "Ready",
                    "lastTransitionTime": "2026-08-28T01:00:45Z",
                },
            ],
            "containerStatuses": [
                {
                    "restartCount": 1,
                    "state": {"running": {"startedAt": "2026-08-28T01:00:10Z"}},
                },
                {
                    "restartCount": 0,
                    "state": {"running": {"startedAt": "2026-08-28T01:00:12Z"}},
                },
            ],
        },
    }

    summary = summarize_pod(pod)

    assert summary["pod"] == {
        "name": "qwen-predictor-abc",
        "namespace": "qwen-serving",
        "phase": "Running",
        "container_count": 2,
        "restart_count": 1,
    }
    assert summary["durations_seconds"] == {
        "scheduling": 2.0,
        "container_start": 10.0,
        "containers_ready": 42.0,
        "ready": 45.0,
        "container_to_ready": 35.0,
    }
    assert "uid" not in str(summary)
