# ============================================================
#  공매도 대시보드 일일 갱신 (저장소 폴더에서 실행)
#    powershell -ExecutionPolicy Bypass -File .\update.ps1
#    powershell -ExecutionPolicy Bypass -File .\update.ps1 -Days 10        # 최근 10일만 보강
#    powershell -ExecutionPolicy Bypass -File .\update.ps1 -SkipKrxShort   # KRX 공매도 건너뛰기
#
#  사전 조건: launch_chrome.ps1 로 크롬을 띄우고 data.krx.co.kr 에 로그인.
#             (KRX 공매도 잔고/거래량만 로그인이 필요합니다.
#              시세는 OPEN API, 유동주식수는 FnGuide, 대차잔고는 KOFIA — 모두 불필요.)
# ============================================================
param(
    [int]$Days = 7,
    [switch]$SkipKrxShort,
    [switch]$SkipFloat
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$end   = (Get-Date).ToString("yyyyMMdd")
$start = (Get-Date).AddDays(-$Days * 2).ToString("yyyyMMdd")   # 휴일 감안 여유

function Step($n, $msg) { Write-Host "`n=== [$n] $msg ===" -ForegroundColor Cyan }

Step 1 "KRX OPEN API 시세 · 상장주식수 ($start ~ $end)"
py scripts\krx_open.py --start $start --end $end --workers 4

Step 2 "종목 마스터 · 유니버스 (시총 1조 이상 개별 보통주)"
$lastDd = py -c "import pandas as pd; d=pd.read_csv('data/prices.csv',dtype={'date':str}); print(sorted(d['date'].unique())[-1])"
py scripts\build_master.py --date $lastDd

if (-not $SkipFloat) {
    Step 3 "FnGuide 유동주식수 (7일 캐시)"
    py scripts\fnguide_float.py --workers 8 --max-age-days 7
} else {
    Write-Host "`n=== [3] 유동주식수 건너뜀 ===" -ForegroundColor DarkGray
}

Step 4 "KOFIA 대차잔고 (로그인 불필요)"
$loanStart = (Get-Date).AddDays(-210).ToString("yyyyMMdd")
py scripts\kofia_loan.py --start $loanStart --end $end --workers 4 --no-cache

if (-not $SkipKrxShort) {
    Step 5 "KRX 공매도 잔고 · 거래량 (로그인 세션 필요, 레이트리밋 적용)"
    py scripts\krx_short.py --start $start --end $end --workers 2
} else {
    Write-Host "`n=== [5] KRX 공매도 수집 건너뜀 — 캐시로 복원 ===" -ForegroundColor DarkGray
    py scripts\krx_short.py --from-cache
}

Step 6 "커버리지 점검"
py scripts\coverage.py

Step 7 "알파·베타 회귀 추정 및 D일 추정잔고"
py scripts\estimate.py --window 60 --min-obs 20 --min-r2 0.05

Step 8 "대시보드 데이터 생성"
py scripts\build_dashboard.py

Write-Host "`n완료. 대시보드 실행:  powershell -ExecutionPolicy Bypass -File $PSScriptRoot\serve.ps1" -ForegroundColor Green
Write-Host "                      http://127.0.0.1:8765/`n"
