[CmdletBinding()]
param(
    [int]$DockerTimeoutSeconds = 180,
    [switch]$RecoverFailedGpuPod
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$dockerRoot = Join-Path $env:LOCALAPPDATA 'Programs\DockerDesktop'
$dockerDesktop = Join-Path $dockerRoot 'Docker Desktop.exe'
$docker = Join-Path $dockerRoot 'resources\bin\docker.exe'

if (-not (Test-Path -LiteralPath $dockerDesktop) -or -not (Test-Path -LiteralPath $docker)) {
    throw 'Docker Desktop was not found.'
}

& $docker info *> $null
if ($LASTEXITCODE -ne 0) {
    Start-Process -FilePath $dockerDesktop -WindowStyle Hidden
}

$deadline = (Get-Date).AddSeconds($DockerTimeoutSeconds)
$dockerReady = $false
do {
    & $docker info *> $null
    if ($LASTEXITCODE -eq 0) {
        $dockerReady = $true
        break
    }
    Start-Sleep -Seconds 2
} while ((Get-Date) -lt $deadline)

if (-not $dockerReady) {
    throw "Docker Desktop was not ready within ${DockerTimeoutSeconds} seconds."
}

$wslDockerReady = $false
$deadline = (Get-Date).AddSeconds(30)
do {
    & wsl.exe -d Ubuntu -- bash -lc 'docker version >/dev/null 2>&1'
    if ($LASTEXITCODE -eq 0) {
        $wslDockerReady = $true
        break
    }
    Start-Sleep -Seconds 2
} while ((Get-Date) -lt $deadline)

if (-not $wslDockerReady) {
    Write-Output 'Docker Desktop WSL Integration is not ready; restarting Docker Desktop once.'
    & $docker desktop restart
    if ($LASTEXITCODE -ne 0) { throw 'Docker Desktop restart failed.' }

    $deadline = (Get-Date).AddSeconds($DockerTimeoutSeconds)
    do {
        & wsl.exe -d Ubuntu -- bash -lc 'docker version >/dev/null 2>&1'
        if ($LASTEXITCODE -eq 0) {
            $wslDockerReady = $true
            break
        }
        Start-Sleep -Seconds 2
    } while ((Get-Date) -lt $deadline)
}

if (-not $wslDockerReady) {
    throw 'Docker Desktop WSL Integration for Ubuntu is unavailable. Enable Ubuntu in Docker Desktop > Settings > Resources > WSL Integration.'
}

$minikubeHost = & wsl.exe -d Ubuntu -- bash -lc 'minikube status --profile=qwen-wsl2-gpu --format="{{.Host}}" 2>/dev/null'
if ($LASTEXITCODE -ne 0 -or ($minikubeHost -join '').Trim() -ne 'Running') {
    & wsl.exe -d Ubuntu -- bash -lc 'minikube start --profile=qwen-wsl2-gpu'
    if ($LASTEXITCODE -ne 0) { throw 'Minikube start failed.' }
}

& wsl.exe -d Ubuntu -- bash -lc 'kubectl --namespace kube-system rollout status daemonset/nvidia-device-plugin-daemonset --timeout=5m'
if ($LASTEXITCODE -ne 0) { throw 'NVIDIA device plugin is not ready.' }

& wsl.exe -d Ubuntu -- bash -lc 'kubectl --namespace kserve rollout status deployment/kserve-controller-manager --timeout=5m'
if ($LASTEXITCODE -ne 0) { throw 'KServe controller is not ready.' }

$failedGpuPods = & wsl.exe -d Ubuntu -- bash -lc 'kubectl --namespace qwen-serving get pods --selector=serving.kserve.io/inferenceservice=qwen-vllm-gpu --field-selector=status.phase=Failed --output=name'
if ($LASTEXITCODE -ne 0) { throw 'Failed to inspect failed GPU Pods.' }
if ($failedGpuPods) {
    if (-not $RecoverFailedGpuPod) {
        throw 'A failed GPU Pod exists. Run again with -RecoverFailedGpuPod to allow its recreation.'
    }
    & wsl.exe -d Ubuntu -- bash -lc 'kubectl --namespace qwen-serving delete pod --selector=serving.kserve.io/inferenceservice=qwen-vllm-gpu --field-selector=status.phase=Failed'
    if ($LASTEXITCODE -ne 0) { throw 'Failed to recreate the failed GPU Pod.' }
}

& wsl.exe -d Ubuntu -- bash -lc 'kubectl --namespace qwen-serving wait --for=create pod --selector=serving.kserve.io/inferenceservice=qwen-vllm-gpu --timeout=5m && kubectl --namespace qwen-serving wait --for=condition=Ready pod --selector=serving.kserve.io/inferenceservice=qwen-vllm-gpu --timeout=20m'
if ($LASTEXITCODE -ne 0) { throw 'The Qwen model is not ready.' }

& wsl.exe -d Ubuntu -- bash -lc 'kubectl --namespace qwen-serving wait --for=condition=Ready pod --selector=app=qwen-gateway --timeout=5m'
if ($LASTEXITCODE -ne 0) { throw 'The gateway is not ready.' }

$forward = Get-NetTCPConnection -State Listen -LocalPort 18000 -ErrorAction SilentlyContinue
if (-not $forward) {
    $logDirectory = Join-Path $env:LOCALAPPDATA 'qwen-serving'
    New-Item -ItemType Directory -Force -Path $logDirectory | Out-Null
    $arguments = '-d Ubuntu -- bash -lc "exec kubectl --namespace qwen-serving port-forward --address 127.0.0.1 service/qwen-gateway 18000:80"'
    Start-Process -FilePath "$env:WINDIR\System32\wsl.exe" -ArgumentList $arguments -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $logDirectory 'gateway-forward.out.log') `
        -RedirectStandardError (Join-Path $logDirectory 'gateway-forward.err.log')
}

$deadline = (Get-Date).AddSeconds(60)
$response = $null
do {
    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:18000/readyz' -TimeoutSec 3
        if ($response.StatusCode -eq 200) { break }
    } catch {
        Start-Sleep -Seconds 2
    }
} while ((Get-Date) -lt $deadline)

if (-not $response -or $response.StatusCode -ne 200) {
    throw 'The gateway localhost forwarding is not ready.'
}

Write-Output 'READY: localhost=http://127.0.0.1:18000 lan=http://<WINDOWS_LAN_IP>:8000'
