from pathlib import Path

STACK = Path(__file__).parent


def test_windows_start_and_lan_exposure_are_gateway_only() -> None:
    start = (STACK / "scripts/start.ps1").read_text(encoding="utf-8")
    install = (STACK / "scripts/install-lan-port.ps1").read_text(encoding="utf-8")

    assert "minikube start --profile=qwen-wsl2-gpu" in start
    assert 'minikube status --profile=qwen-wsl2-gpu --format="{{.Host}}"' in start
    assert "[switch]$RecoverFailedGpuPod" in start
    assert "docker version >/dev/null 2>&1" in start
    assert "desktop restart" in start
    assert "Docker Desktop WSL Integration for Ubuntu is unavailable" in start
    assert "daemonset/nvidia-device-plugin-daemonset" in start
    assert "deployment/kserve-controller-manager" in start
    assert "--field-selector=status.phase=Failed" in start
    assert "service/qwen-gateway 18000:80" in start
    assert "--address 127.0.0.1" in start
    assert "listenport=8000" in install
    assert "connectaddress=127.0.0.1" in install
    assert "connectport=18000" in install
    assert "-Profile Private" in install
    assert "-RemoteAddress LocalSubnet" in install

    combined = start + install
    assert "argocd-server" not in combined
    assert "qwen-vllm-gpu-predictor" not in combined
    assert "6443" not in combined
