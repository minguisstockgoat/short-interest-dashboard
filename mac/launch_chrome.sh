#!/usr/bin/env bash
# ============================================================
#  KRX 로그인용 크롬 실행 (원격 디버깅 포트 9222) — macOS
#
#    bash mac/launch_chrome.sh
#
#  - 전용 프로필(.chrome-profile)을 쓰므로 평소 쓰는 크롬 프로필은 건드리지 않는다.
#  - 창이 뜨면 KRX 로그인 페이지에서 직접 로그인한다.
#  - 맥미니는 상시 구동이므로 이 크롬 창을 그냥 열어두면 된다.
#    세션이 만료되면 다시 로그인만 해주면 이후 수집이 자동으로 재개된다.
# ============================================================
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROFILE="$ROOT/.chrome-profile"
LOGIN_URL="https://data.krx.co.kr/contents/MDC/COMS/client/MDCCOMS001.cmd"

CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
if [[ ! -x "$CHROME" ]]; then
  CHROME="$HOME/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
fi
if [[ ! -x "$CHROME" ]]; then
  echo "크롬을 찾지 못했습니다. Google Chrome을 설치해주세요." >&2
  exit 1
fi

mkdir -p "$PROFILE"

# 이미 9222가 열려 있으면 중복 실행하지 않는다
if curl -fsS --max-time 2 http://127.0.0.1:9222/json/version >/dev/null 2>&1; then
  echo "이미 디버깅 크롬이 실행 중입니다 (127.0.0.1:9222)."
  echo "로그인 상태 확인:  python3 scripts/krx_session.py"
  exit 0
fi

echo
echo "  크롬 실행: $CHROME"
echo "  프로필   : $PROFILE"
echo "  디버깅   : http://127.0.0.1:9222"
echo
echo "  >> 열리는 창에서 KRX 로그인을 완료하세요."
echo "  >> 맥미니는 이 창을 계속 열어두면 매일 자동 수집됩니다."
echo

# --restore-last-session 은 필수다. KRX 로그인 쿠키가 세션 쿠키라, 복원을 끄면
# 크롬을 다시 띄울 때마다 네이버 로그인을 새로 해야 한다.
nohup "$CHROME" \
  --remote-debugging-port=9222 \
  --remote-allow-origins='*' \
  --user-data-dir="$PROFILE" \
  --no-first-run \
  --no-default-browser-check \
  --restore-last-session \
  "$LOGIN_URL" >/dev/null 2>&1 &

sleep 3
if curl -fsS --max-time 3 http://127.0.0.1:9222/json/version >/dev/null 2>&1; then
  echo "크롬 기동 완료. 로그인 후 아래로 확인하세요:"
  echo "  python3 scripts/krx_session.py"
else
  echo "크롬이 아직 준비되지 않았습니다. 몇 초 뒤 다시 확인해보세요." >&2
fi
