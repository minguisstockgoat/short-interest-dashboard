#!/usr/bin/env bash
# ============================================================
#  대시보드 '수동 갱신' 버튼을 받는 로컬 에이전트 (launchd 진입점)
#
#    bash mac/agent.sh                    # 127.0.0.1:8766
#    AGENT_HOST=0.0.0.0 bash mac/agent.sh # 같은 네트워크에 개방
#
#  브라우저는 https 페이지에서 http 로 나가는 요청을 막지만 localhost 는
#  예외다. 즉 이 맥미니에서 대시보드를 열면 버튼이 활성화된다.
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

exec "$PY" scripts/refresh_agent.py \
  --host "${AGENT_HOST:-127.0.0.1}" --port "${AGENT_PORT:-8766}" "$@"
