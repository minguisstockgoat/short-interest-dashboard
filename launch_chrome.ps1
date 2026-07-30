# ============================================================
#  KRX 로그인용 크롬 실행 (원격 디버깅 포트 9222)
#
#  사용법: 새 PowerShell 창에서 (저장소 폴더로 이동 후)
#      powershell -ExecutionPolicy Bypass -File .\launch_chrome.ps1
#
#  - 기존 크롬 프로필을 건드리지 않도록 전용 프로필(.chrome-profile)을 씁니다.
#  - 창이 뜨면 KRX 로그인 페이지에서 직접 로그인하세요.
#  - 로그인 후 이 창은 그대로 두시면 됩니다 (닫으면 세션이 끊깁니다).
# ============================================================

$ErrorActionPreference = "Stop"

$chrome = @(
    "C:\Program Files\Google\Chrome\Application\chrome.exe",
    "C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe"
) | Where-Object { Test-Path $_ } | Select-Object -First 1

if (-not $chrome) { throw "chrome.exe 를 찾지 못했습니다." }

$profileDir = Join-Path $PSScriptRoot ".chrome-profile"
if (-not (Test-Path $profileDir)) { New-Item -ItemType Directory -Path $profileDir | Out-Null }

$loginUrl = "https://data.krx.co.kr/contents/MDC/COMS/client/MDCCOMS001.cmd"

Write-Host ""
Write-Host "  크롬 실행: $chrome"
Write-Host "  프로필   : $profileDir"
Write-Host "  디버깅   : http://127.0.0.1:9222"
Write-Host ""
Write-Host "  >> 열리는 창에서 KRX 로그인을 완료한 뒤, Claude 에게 '로그인 완료' 라고 알려주세요."
Write-Host "  >> 이 터미널 창과 크롬 창은 수집이 끝날 때까지 닫지 마세요."
Write-Host ""

& $chrome `
    --remote-debugging-port=9222 `
    --remote-allow-origins=* `
    --user-data-dir="$profileDir" `
    --no-first-run `
    --no-default-browser-check `
    $loginUrl
