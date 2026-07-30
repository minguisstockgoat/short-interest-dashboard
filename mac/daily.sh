#!/usr/bin/env bash
# ============================================================
#  일일 갱신 + GitHub Pages 배포 (macOS / launchd 진입점)
#
#    bash mac/daily.sh              # 갱신 + 배포
#    bash mac/daily.sh --no-deploy  # 갱신만
#
#  launchd는 로그인 셸 환경을 물려받지 않으므로 .env 를 명시적으로 읽는다.
# ============================================================
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

mkdir -p logs
LOG="logs/daily_$(date +%Y%m%d_%H%M%S).log"
exec > >(tee -a "$LOG") 2>&1

echo "[$(date '+%F %T')] === 일일 갱신 시작 (macOS) ==="

# --- 환경변수 ------------------------------------------------------------
if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi
if [[ -z "${KRX_API_KEY:-}" ]]; then
  echo "중단: KRX_API_KEY 가 없습니다. .env 를 확인하세요."
  exit 1
fi

# --- 파이썬 --------------------------------------------------------------
if [[ -x .venv/bin/python ]]; then
  PY=".venv/bin/python"
else
  PY="$(command -v python3 || true)"
fi
if [[ -z "$PY" ]]; then
  echo "중단: python3 를 찾을 수 없습니다. bash mac/setup.sh 를 먼저 실행하세요."
  exit 1
fi
echo "파이썬: $PY ($($PY --version 2>&1))"

# --- PATH 보정 (launchd는 최소 PATH만 준다) ------------------------------
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH"

DEPLOY="--deploy"
for arg in "$@"; do
  [[ "$arg" == "--no-deploy" ]] && DEPLOY=""
done

"$PY" scripts/pipeline.py --days "${DAYS:-7}" $DEPLOY
CODE=$?

echo "[$(date '+%F %T')] === 종료 (exit=$CODE) ==="

# 30일 지난 로그 정리
find logs -name 'daily_*.log' -mtime +30 -delete 2>/dev/null || true

exit $CODE
