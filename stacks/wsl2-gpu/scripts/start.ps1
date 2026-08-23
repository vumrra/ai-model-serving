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
    throw 'Docker Desktop을 찾을 수 없습니다.'
}

& $docker info *> $null
if ($LASTEXITCODE -ne 0) {
    Start-Process -FilePath $dockerDesktop -WindowStyle Hidden
}

$deadline = (Get-Date).AddSeconds($DockerTimeoutSeconds)
do {
    & $docker info *> $null
    if ($LASTEXITCODE -eq 0) { break }
    Start-Sleep -Seconds 2
} while ((Get-Date) -lt $deadline)

if ($LASTEXITCODE -ne 0) {
    throw "Docker Desktop이 ${DockerTimeoutSeconds}초 안에 준비되지 않았습니다."
}

& wsl.exe -d Ubuntu -- bash -lc 'minikube start --profile=qwen-wsl2-gpu'
if ($LASTEXITCODE -ne 0) { throw 'Minikube 시작에 실패했습니다.' }

& wsl.exe -d Ubuntu -- bash -lc 'kubectl --namespace kube-system rollout status daemonset/nvidia-device-plugin-daemonset --timeout=5m'
if ($LASTEXITCODE -ne 0) { throw 'NVIDIA device plugin이 준비되지 않았습니다.' }

& wsl.exe -d Ubuntu -- bash -lc 'kubectl --namespace kserve rollout status deployment/kserve-controller-manager --timeout=5m'
if ($LASTEXITCODE -ne 0) { throw 'KServe controller가 준비되지 않았습니다.' }

$failedGpuPods = & wsl.exe -d Ubuntu -- bash -lc 'kubectl --namespace qwen-serving get pods --selector=serving.kserve.io/inferenceservice=qwen-vllm-gpu --field-selector=status.phase=Failed --output=name'
if ($LASTEXITCODE -ne 0) { throw '실패한 GPU Pod 확인에 실패했습니다.' }
if ($failedGpuPods) {
    if (-not $RecoverFailedGpuPod) {
        throw '실패한 GPU Pod가 있습니다. 재생성을 허용하려면 -RecoverFailedGpuPod 옵션으로 다시 실행하세요.'
    }
    & wsl.exe -d Ubuntu -- bash -lc 'kubectl --namespace qwen-serving delete pod --selector=serving.kserve.io/inferenceservice=qwen-vllm-gpu --field-selector=status.phase=Failed'
    if ($LASTEXITCODE -ne 0) { throw '실패한 GPU Pod 재생성에 실패했습니다.' }
}

& wsl.exe -d Ubuntu -- bash -lc 'kubectl --namespace qwen-serving wait --for=create pod --selector=serving.kserve.io/inferenceservice=qwen-vllm-gpu --timeout=5m && kubectl --namespace qwen-serving wait --for=condition=Ready pod --selector=serving.kserve.io/inferenceservice=qwen-vllm-gpu --timeout=20m'
if ($LASTEXITCODE -ne 0) { throw 'Qwen 모델이 준비되지 않았습니다.' }

& wsl.exe -d Ubuntu -- bash -lc 'kubectl --namespace qwen-serving wait --for=condition=Ready pod --selector=app=qwen-gateway --timeout=5m'
if ($LASTEXITCODE -ne 0) { throw 'Gateway가 준비되지 않았습니다.' }

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
    throw 'Gateway localhost 포워딩이 준비되지 않았습니다.'
}

Write-Output 'READY: localhost=http://127.0.0.1:18000 lan=http://<WINDOWS_LAN_IP>:8000'
