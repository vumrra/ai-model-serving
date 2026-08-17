from scripts.export_release_env import release_environment


def test_release_environment_comes_from_verified_manifest():
    release = {
        "schema_version": "1.0",
        "release_id": "release-1",
        "gateway_image": "registry/gateway@sha256:" + "a" * 64,
        "runtime_image": "registry/runtime@sha256:" + "b" * 64,
        "engine": {"name": "vllm", "version": "0.10.0"},
        "model": {"id": "Qwen/Qwen3-4B", "revision": "c" * 40, "dtype": "bfloat16"},
        "serving": {
            "max_model_len": 8192,
            "tensor_parallel_size": 1,
            "gpu_memory_utilization": 0.9,
            "chat_template_kwargs": {"enable_thinking": False},
        },
        "serving_config_sha256": "d" * 64,
    }

    values = release_environment(release)

    assert values["RUNTIME_IMAGE"].endswith("b" * 64)
    assert values["MODEL_REVISION"] == "c" * 40
    assert values["ENGINE_NAME"] == "vllm"
