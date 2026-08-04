#!/usr/bin/env bash
# ============================================================
#  KRX 로그인 세션 상시 유지 (launchd 진입점)
#
#    bash mac/keepalive.sh              # 30분 주기로 상주
#    bash mac/keepalive.sh --once       # 한 번만 점검
#
#  30분마다 세션을 연장하고, 끊겼으면 .env 계정으로 재로그인한다.
#  연속 실패하면 스스로 멈추고 텔레그램으로 알린다(계정 잠금 방지).
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

exec "$PY" scripts/krx_keepalive.py --interval "${KEEPALIVE_INTERVAL:-1800}" "$@"
