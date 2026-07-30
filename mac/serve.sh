#!/usr/bin/env bash
# 대시보드 로컬 서버 (http://127.0.0.1:8765) — macOS
#   bash mac/serve.sh
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="$ROOT/.venv/bin/python"
[[ -x "$PY" ]] || PY="python3"
echo
echo "  대시보드: http://127.0.0.1:8765/"
echo "  종료: Ctrl+C"
echo
exec "$PY" -m http.server 8765 --directory "$ROOT/docs" --bind 127.0.0.1
