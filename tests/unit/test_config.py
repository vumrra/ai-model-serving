from apps.gateway.config import Settings


def test_settings_reads_environment(monkeypatch):
    monkeypatch.setenv("PUBLIC_MODEL_NAME", "qwen-test")
    monkeypatch.setenv("MAX_COMPLETION_TOKENS", "42")
    monkeypatch.setenv("UPSTREAM_BASE_URL", "http://engine:8001/")

    settings = Settings.from_env()

    assert settings.public_model_name == "qwen-test"
    assert settings.max_completion_tokens == 42
    assert settings.upstream_base_url == "http://engine:8001"


def test_settings_reads_deployment_environment_names(monkeypatch):
    monkeypatch.setenv("PUBLIC_API_KEY", "public-key")
    monkeypatch.setenv("ENGINE_API_KEY", "engine-key")
    monkeypatch.setenv("ENGINE_BASE_URL", "http://engine:8000/")
    monkeypatch.setenv("ENGINE_MODEL_NAME", "Qwen/Qwen3-4B")
    monkeypatch.setenv("MODEL_ALIAS", "qwen3-4b")

    settings = Settings.from_env()

    assert settings.api_key == "public-key"
    assert settings.upstream_api_key == "engine-key"
    assert settings.upstream_base_url == "http://engine:8000"
    assert settings.upstream_model_name == "Qwen/Qwen3-4B"
    assert settings.public_model_name == "qwen3-4b"
