#!/usr/bin/env bash
# ============================================================
#  KRX 로그인 세션 상시 유지 (launchd 진입점)
#
#    bash mac/keepalive.sh              # 20분 주기로 상주
#    bash mac/keepalive.sh --once       # 한 번만 점검
#
#  20분마다 세션을 연장한다. KRX 유휴 만료가 30분이라, 주기를 30분으로 두면
#  만료 경계와 겹쳐 매번 놓친다. 끊겼으면 krx_login 에 복구를 맡기고,
#  사람의 네이버 로그인이 필요하면 텔레그램으로 알린 뒤 조용히 기다린다.
# ============================================================
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

if [[ -x .venv/bin/python ]]; then
  PY=".venv/bin/python"
else
  PY="$(command -v python3 || true)"
fi
[[ -z "$PY" ]] && { echo "python3 없음 — bash mac/setup.sh 먼저"; exit 1; }

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH"

exec "$PY" scripts/krx_keepalive.py --interval "${KEEPALIVE_INTERVAL:-1200}" "$@"
