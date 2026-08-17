from deploy.runpod.cleanup_expired import is_expired_managed_pod


def test_cleanup_only_matches_expired_project_pods():
    now = 2_000
    assert is_expired_managed_pod({"name": "qwen-serving-lab-demo-release-1-exp1999"}, now)
    assert not is_expired_managed_pod({"name": "another-project-demo-exp1999"}, now)
    assert not is_expired_managed_pod({"name": "qwen-serving-lab-demo-release-1-exp2001"}, now)
