#Requires -RunAsAdministrator

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object Security.Principal.WindowsPrincipal($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw '관리자 PowerShell에서 실행해야 합니다.'
}

Set-Service -Name iphlpsvc -StartupType Automatic
Start-Service -Name iphlpsvc

& netsh.exe interface portproxy set v4tov4 listenaddress=0.0.0.0 listenport=8000 connectaddress=127.0.0.1 connectport=18000
if ($LASTEXITCODE -ne 0) {
    & netsh.exe interface portproxy add v4tov4 listenaddress=0.0.0.0 listenport=8000 connectaddress=127.0.0.1 connectport=18000
}
if ($LASTEXITCODE -ne 0) { throw 'Windows portproxy 설정에 실패했습니다.' }

$ruleName = 'Qwen Gateway LAN 8000'
$rule = Get-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue
if ($rule) {
    $rule | Set-NetFirewallRule -Enabled True -Profile Private -Direction Inbound -Action Allow
    $rule | Get-NetFirewallPortFilter | Set-NetFirewallPortFilter -Protocol TCP -LocalPort 8000
    $rule | Get-NetFirewallAddressFilter | Set-NetFirewallAddressFilter -RemoteAddress LocalSubnet
} else {
    New-NetFirewallRule -DisplayName $ruleName -Enabled True -Profile Private -Direction Inbound `
        -Action Allow -Protocol TCP -LocalPort 8000 -RemoteAddress LocalSubnet | Out-Null
}

Write-Output 'INSTALLED: Windows TCP 8000 -> 127.0.0.1:18000, Private/LocalSubnet only'
