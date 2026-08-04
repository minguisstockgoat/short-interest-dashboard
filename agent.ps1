# ============================================================
#  대시보드 '수동 갱신' 버튼을 받는 로컬 에이전트 (Windows 진입점)
#
#    powershell -ExecutionPolicy Bypass -File .\agent.ps1
#
#  로그온 시 자동 시작 등록:  .\install_agent.ps1
#
#  브라우저는 https 페이지에서 http 로 나가는 요청을 막지만 localhost 는
#  예외다. 즉 이 컴퓨터에서 대시보드를 열면 '수동 갱신' 버튼이 활성화된다.
#  (맥미니의 mac/agent.sh 와 같은 역할 — scripts/refresh_agent.py 를 띄운다)
# ============================================================
param(
    [string]$AgentHost = "127.0.0.1",
    [int]$Port = 8766
)

Set-Location $PSScriptRoot

$logDir = Join-Path $PSScriptRoot "logs"
if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir | Out-Null }
$log = Join-Path $logDir "agent.log"

# PATH 의 python.exe 는 스토어 스텁일 수 있어 py 런처로 실제 경로를 찾는다
$py = & py -3 -c "import sys; print(sys.executable)" 2>$null
if (-not $py) { throw "Python 3 을 찾을 수 없습니다 (py 런처 필요)" }

"[{0}] 에이전트 시작 {1}:{2} ({3})" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $AgentHost, $Port, $py |
    Add-Content -Path $log -Encoding UTF8

& $py (Join-Path $PSScriptRoot "scripts\refresh_agent.py") --host $AgentHost --port $Port *>> $log
