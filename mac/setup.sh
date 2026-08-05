#!/usr/bin/env bash
# ============================================================
#  맥미니 최초 셋업
#
#    bash mac/setup.sh
#
#  가상환경 생성 → 의존성 설치 → 환경변수 파일(.env) 생성 안내 → 점검
# ============================================================
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "=== 1. 파이썬 확인 ==="
if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 가 없습니다. 아래 중 하나로 설치하세요:" >&2
  echo "  brew install python@3.12      (Homebrew)" >&2
  echo "  또는 https://www.python.org/downloads/macos/" >&2
  exit 1
fi
python3 --version

echo
echo "=== 2. 가상환경 (.venv) ==="
if [[ ! -d .venv ]]; then
  python3 -m venv .venv
  echo "생성됨: $ROOT/.venv"
else
  echo "이미 존재: $ROOT/.venv"
fi
# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip install --quiet --upgrade pip
python -m pip install --quiet pandas numpy requests websocket-client
echo "의존성 설치 완료: pandas numpy requests websocket-client"

echo
echo "=== 3. 환경변수 (.env) ==="
if [[ ! -f .env ]]; then
  cat > .env <<'EOF'
# KRX Data Marketplace OPEN API 인증키 (필수)
#   https://data.krx.co.kr → OPEN API 신청 후 발급받은 키
KRX_API_KEY=

# KRX 정보데이터시스템 로그인은 네이버 SSO 라서 .env 에 계정을 넣지 않는다.
#   bash mac/launch_chrome.sh 로 전용 프로필 크롬을 띄우고 사람이 한 번 로그인하면,
#   프로필에 쿠키가 남아 이후 수집이 그 세션을 빌려 쓴다(30분마다 자동 연장).

# 텔레그램 알림 (선택이지만 강력 권장 — 무인 실행의 실패를 알아채는 유일한 통로)
#   봇 생성: @BotFather → /newbot
#   챗 ID  : 봇에게 아무 메시지나 보낸 뒤
#            https://api.telegram.org/bot<TOKEN>/getUpdates 의 chat.id
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=

# 수동 갱신 에이전트 (선택)
#   127.0.0.1 로만 열 거라면 토큰 없이 두어도 된다.
#   AGENT_HOST=0.0.0.0 으로 개방한다면 반드시 토큰을 설정하세요.
# AGENT_HOST=127.0.0.1
# AGENT_PORT=8766
# AGENT_TOKEN=
EOF
  chmod 600 .env
  echo ".env 생성됨 — KRX_API_KEY 값을 채워주세요:"
  echo "  nano $ROOT/.env"
else
  echo "이미 존재: $ROOT/.env"
fi

echo
echo "=== 4. git / gh 확인 ==="
command -v git >/dev/null 2>&1 && git --version || echo "git 없음 (Xcode CLT 설치 필요: xcode-select --install)"
if command -v gh >/dev/null 2>&1; then
  gh --version | head -1
  gh auth status 2>&1 | head -3 || true
else
  echo "gh 없음 — 배포하려면 설치 후 로그인하세요:"
  echo "  brew install gh && gh auth login"
fi

echo
echo "=== 다음 단계 ==="
echo "  1) .env 에 KRX_API_KEY / TELEGRAM_* 입력"
echo "  2) 데이터 이관:  Windows에서 만든 bootstrap 아카이브를 data/ 로 풀기"
echo "     (없으면 처음부터 수집되지만 KRX 요청이 많아 시간이 걸립니다)"
echo "  3) .venv/bin/python scripts/notify.py   → 텔레그램 알림 도착 확인"
echo "  4) bash mac/launch_chrome.sh    → 전용 크롬이 뜨면 네이버로 KRX 로그인 (사람이 1회)"
echo "  5) .venv/bin/python scripts/krx_login.py --status  → 세션 유효 확인"
echo "  6) bash mac/doctor.sh          → 환경 점검"
echo "  7) bash mac/daily.sh           → 수동 1회 실행"
echo "  8) bash mac/install_schedule.sh → 평일 22:00 자동 실행 + 세션유지 + 갱신버튼 등록"
echo
