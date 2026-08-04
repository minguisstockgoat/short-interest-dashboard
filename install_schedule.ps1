# ============================================================
#  일일 자동 갱신 작업 등록 (Windows 작업 스케줄러)
#
#    powershell -ExecutionPolicy Bypass -File .\install_schedule.ps1
#    powershell -ExecutionPolicy Bypass -File .\install_schedule.ps1 -Time "20:00"
#    powershell -ExecutionPolicy Bypass -File .\install_schedule.ps1 -Uninstall
#
#  평일에 지정 시각으로 daily.ps1 을 실행한다.
#  1차 실행이 실패하면 2시간 뒤까지 30분 간격으로 재시도한다.
# ============================================================
param(
    [string]$Time = "22:00",
    [string]$TaskName = "ShortInterestDashboard",
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

$script = Join-Path $PSScriptRoot "daily.ps1"
if (-not (Test-Path $script)) { throw "daily.ps1 을 찾을 수 없습니다: $script" }

$action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$script`"" `
    -WorkingDirectory $PSScriptRoot

$trigger = New-ScheduledTaskTrigger -Weekly `
    -DaysOfWeek Monday, Tuesday, Wednesday, Thursday, Friday -At $Time

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -DontStopOnIdleEnd `
    -RestartCount 4 `
    -RestartInterval (New-TimeSpan -Minutes 30) `
    -ExecutionTimeLimit (New-TimeSpan -Hours 2) `
    -MultipleInstances IgnoreNew

# 로그온한 사용자 계정으로 실행 (크롬 세션 접근에 필요)
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
    -Settings $settings -Principal $principal -Force `
    -Description "국내 공매도 잔고 대시보드 일일 갱신 및 GitHub Pages 배포" | Out-Null

Write-Host ""
Write-Host "  작업 등록 완료" -ForegroundColor Green
Write-Host "    이름   : $TaskName"
Write-Host "    시각   : 평일 $Time (실패 시 30분 간격 4회 재시도)"
Write-Host "    스크립트: $script"
Write-Host ""
Write-Host "  즉시 테스트:  Start-ScheduledTask -TaskName $TaskName"
Write-Host "  상태 확인  :  Get-ScheduledTaskInfo -TaskName $TaskName"
Write-Host "  삭제       :  .\install_schedule.ps1 -Uninstall"
Write-Host ""
Write-Host "  주의: KRX 공매도 데이터는 크롬 로그인 세션이 필요합니다." -ForegroundColor Yellow
Write-Host "        launch_chrome.ps1 로 띄운 크롬을 로그인 상태로 두면 자동 수집되고," -ForegroundColor Yellow
Write-Host "        없으면 나머지(시세/유동주식수/대차잔고)만 갱신됩니다." -ForegroundColor Yellow
Write-Host ""
