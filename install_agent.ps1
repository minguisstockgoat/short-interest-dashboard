# ============================================================
#  수동 갱신 에이전트 자동 시작 등록 (Windows 작업 스케줄러)
#
#    powershell -ExecutionPolicy Bypass -File .\install_agent.ps1
#    powershell -ExecutionPolicy Bypass -File .\install_agent.ps1 -Uninstall
#
#  로그온할 때 agent.ps1 을 숨김 창으로 띄워 둔다. 에이전트가 떠 있으면
#  이 컴퓨터에서 대시보드를 열었을 때 '수동 갱신' 버튼이 활성화된다.
# ============================================================
param(
    [string]$TaskName = "ShortDashboardAgent",
    [switch]$Uninstall
)

$ErrorActionPreference = "Stop"

if ($Uninstall) {
    try {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
        Write-Host "작업 '$TaskName' 삭제됨" -ForegroundColor Green
    } catch {
        Write-Host "등록된 작업이 없습니다." -ForegroundColor Yellow
    }
    return
}

$script = Join-Path $PSScriptRoot "agent.ps1"
if (-not (Test-Path $script)) { throw "agent.ps1 을 찾을 수 없습니다: $script" }

$action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$script`"" `
    -WorkingDirectory $PSScriptRoot

$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) `
    -MultipleInstances IgnoreNew

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
    -Settings $settings -Description "공매도 대시보드 수동 갱신 에이전트 (127.0.0.1:8766)" -Force | Out-Null

Write-Host "작업 '$TaskName' 등록됨 (로그온 시 자동 시작)" -ForegroundColor Green
Write-Host "지금 바로 시작하려면: Start-ScheduledTask -TaskName $TaskName"
