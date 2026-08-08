#!/usr/bin/env bash
# ============================================================
#  KRX 로그인 감시 (launchd 진입점)
#
#    bash mac/keepalive.sh              # 5분 주기로 상주
#    bash mac/keepalive.sh --once       # 한 번만 점검
#
#  KRX 세션은 로그인 후 약 30분이면 활동과 무관하게 끊긴다 — 연장이 불가능하다.
#  그래서 붙들어두려 하지 않고, 사람이 하루 한 번 로그인하는 그 순간을 감지해
#  곧바로 갱신을 돌린다. 정해진 시각까지 로그인이 없으면 한 번만 알린다.
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

exec "$PY" scripts/krx_keepalive.py --interval "${KEEPALIVE_INTERVAL:-300}" "$@"
