# ============================================================
#  일일 자동 갱신 + GitHub Pages 배포
#
#  작업 스케줄러가 호출하는 진입점. update.ps1 로 데이터를 갱신한 뒤
#  docs/ 변경분만 커밋·푸시하면 Pages가 자동 재배포된다.
#
#  수동 실행:  powershell -ExecutionPolicy Bypass -File .\daily.ps1
#  등록:       powershell -ExecutionPolicy Bypass -File .\install_schedule.ps1
#
#  KRX 공매도(잔고/거래량)만 로그인 세션이 필요하다. 크롬이 안 떠 있거나
#  로그인이 풀렸으면 그 단계만 건너뛰고 나머지를 갱신한 뒤 로그에 남긴다.
# ============================================================
param(
    [int]$Days = 7,
    [switch]$NoPush
)

Set-Location $PSScriptRoot
$ErrorActionPreference = "Continue"

$logDir = Join-Path $PSScriptRoot "logs"
if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir | Out-Null }
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$log = Join-Path $logDir "daily_$stamp.log"

function Say($msg) {
    $line = "[{0}] {1}" -f (Get-Date -Format "HH:mm:ss"), $msg
    Write-Host $line
    Add-Content -Path $log -Value $line -Encoding UTF8
}

Say "=== 일일 갱신 시작 ==="

# --- KRX 로그인 세션 확인 -------------------------------------------------
$krxOk = $false
try {
    $null = py scripts\krx_session.py 2>&1
    if ($LASTEXITCODE -eq 0) { $krxOk = $true }
} catch { }

if ($krxOk) {
    Say "KRX 로그인 세션 확인됨 — 공매도 포함 전체 갱신"
    $out = powershell -ExecutionPolicy Bypass -File "$PSScriptRoot\update.ps1" -Days $Days 2>&1
} else {
    Say "KRX 세션 없음 — 공매도 제외하고 갱신 (크롬 로그인 후 재실행 권장)"
    $out = powershell -ExecutionPolicy Bypass -File "$PSScriptRoot\update.ps1" -Days $Days -SkipKrxShort 2>&1
}
$out | ForEach-Object { Add-Content -Path $log -Value $_ -Encoding UTF8 }
Say "데이터 갱신 종료 (exit=$LASTEXITCODE)"

# --- 산출물 검증 ----------------------------------------------------------
$json = Join-Path $PSScriptRoot "docs\dashboard_data.json"
if (-not (Test-Path $json)) { Say "중단: dashboard_data.json 없음"; exit 1 }
$size = (Get-Item $json).Length
if ($size -lt 500KB) { Say "중단: dashboard_data.json 이 비정상적으로 작음 ($size bytes)"; exit 1 }

$meta = (Get-Content $json -Raw -Encoding UTF8 | ConvertFrom-Json).meta
Say "기준일 $($meta.asof) / 확정일 $($meta.knownDate) / $($meta.universe)종목 / $([math]::Round($size/1MB,2)) MB"

# --- 커밋 & 푸시 ----------------------------------------------------------
if ($NoPush) { Say "NoPush 지정 — 배포 생략"; exit 0 }

$changed = git status --porcelain -- docs
if (-not $changed) { Say "docs 변경 없음 — 배포 생략"; exit 0 }

git add docs
git commit -q -m "데이터 갱신 $($meta.asof) (확정 $($meta.knownDate))"
if ($LASTEXITCODE -ne 0) { Say "커밋 실패"; exit 1 }

git push -q origin main 2>&1 | ForEach-Object { Add-Content -Path $log -Value $_ -Encoding UTF8 }
if ($LASTEXITCODE -ne 0) { Say "푸시 실패 — 네트워크/인증 확인"; exit 1 }

Say "배포 완료 → https://minguisstockgoat.github.io/short-interest-dashboard/"

# 30일 지난 로그 정리
Get-ChildItem $logDir -Filter "daily_*.log" |
    Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-30) } |
    Remove-Item -Force -ErrorAction SilentlyContinue

Say "=== 완료 ==="
