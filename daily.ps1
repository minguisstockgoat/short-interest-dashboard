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

# --- KRX 로그인 세션 확보 -------------------------------------------------
#  세션이 없으면 .env 계정으로 자동 로그인을 한 번 시도한다(krx_login.py 가
#  시도 횟수를 제한하므로 여기서 재시도 루프를 돌리지 않는다).
#  이전에는 exit code 를 잘못 읽어 세션이 없는데도 "확인됨"으로 진행했고,
#  그 결과 공매도만 며칠씩 조용히 멈춰 있었다.
$krxOk = $false
try {
    $loginOut = py scripts\krx_login.py 2>&1
    if ($LASTEXITCODE -eq 0) { $krxOk = $true }
    $loginOut | ForEach-Object { Add-Content -Path $log -Value $_ -Encoding UTF8 }
} catch {
    Say "krx_login.py 실행 실패: $_"
}

if ($krxOk) {
    Say "KRX 로그인 세션 확보 — 공매도 포함 전체 갱신"
    $out = powershell -ExecutionPolicy Bypass -File "$PSScriptRoot\update.ps1" -Days $Days 2>&1
} else {
    Say "KRX 세션 확보 실패 — 공매도 제외하고 갱신 (직전 값 유지)"
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
