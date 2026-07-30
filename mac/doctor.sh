#!/usr/bin/env bash
# ============================================================
#  환경 점검 — 맥미니로 옮긴 뒤 무엇이 준비됐고 무엇이 빠졌는지 한 번에 확인
#
#    bash mac/doctor.sh
# ============================================================
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

ok()   { printf "  \033[32m✓\033[0m %s\n" "$1"; }
bad()  { printf "  \033[31m✗\033[0m %s\n" "$1"; FAIL=$((FAIL+1)); }
warn() { printf "  \033[33m!\033[0m %s\n" "$1"; }
FAIL=0

echo
echo "=== 실행 환경 ==="
if [[ -x .venv/bin/python ]]; then
  PY=".venv/bin/python"; ok "가상환경 .venv ($($PY --version 2>&1))"
elif command -v python3 >/dev/null 2>&1; then
  PY="python3"; warn "가상환경 없음, 시스템 python3 사용 ($(python3 --version 2>&1))"
else
  PY=""; bad "python3 없음 — bash mac/setup.sh 실행 필요"
fi

if [[ -n "$PY" ]]; then
  for m in pandas numpy requests websocket; do
    if $PY -c "import $m" 2>/dev/null; then ok "모듈 $m"; else bad "모듈 $m 없음"; fi
  done
fi

echo
echo "=== 자격 정보 ==="
[[ -f .env ]] && set -a && source .env && set +a
if [[ -n "${KRX_API_KEY:-}" ]]; then ok "KRX_API_KEY 설정됨 (${#KRX_API_KEY}자)"
else bad "KRX_API_KEY 없음 — .env 확인"; fi

echo
echo "=== 데이터 ==="
for f in prices.csv universe.csv free_float.csv short_balance.csv short_volume.csv loan_balance.csv; do
  if [[ -f "data/$f" ]]; then
    rows=$(( $(wc -l < "data/$f") - 1 ))
    ok "data/$f (${rows}행)"
  else
    warn "data/$f 없음 — 첫 실행 시 수집됨(시간 소요)"
  fi
done

echo
echo "=== 외부 접근 ==="
if curl -fsS --max-time 8 -H "AUTH_KEY: ${KRX_API_KEY:-x}" \
   "https://data-dbg.krx.co.kr/svc/apis/sto/stk_bydd_trd?basDd=20260729" \
   -o /dev/null 2>/dev/null; then
  ok "KRX OPEN API 응답"
else
  bad "KRX OPEN API 실패 — 인증키 또는 네트워크/IP차단 확인"
fi

if curl -fsS --max-time 8 -X POST "https://freesis.kofia.or.kr/meta/getMetaDataList.do" \
   -H "Content-Type: application/json;charset=UTF-8" \
   -H "Referer: https://freesis.kofia.or.kr/stat/FreeSIS.do" \
   -d '{"dmSearch":{"tmpV1":"D","tmpV45":"20260728","tmpV46":"20260730","tmpV72":"005930","OBJ_NM":"STATSCU0100000140BO"}}' \
   -o /dev/null 2>/dev/null; then
  ok "KOFIA 대차잔고 응답"
else
  bad "KOFIA 응답 실패"
fi

if curl -fsS --max-time 8 "https://wcomp.fnguide.com/CompanyInfo/Snapshot?cmp_cd=005930" \
   -o /dev/null 2>/dev/null; then
  ok "FnGuide 응답"
else
  warn "FnGuide 응답 실패 — 유동주식수 갱신만 영향"
fi

echo
echo "=== KRX 로그인 세션 (공매도 수집용) ==="
if curl -fsS --max-time 3 http://127.0.0.1:9222/json/version >/dev/null 2>&1; then
  ok "디버깅 크롬 실행 중 (9222)"
  if [[ -n "$PY" ]] && $PY scripts/krx_session.py 2>&1 | grep -q "사용 가능"; then
    ok "KRX 로그인 세션 유효 — 공매도 자동 수집 가능"
  else
    warn "크롬은 떠 있으나 KRX 로그인이 안 됨 — 크롬 창에서 로그인하세요"
  fi
else
  warn "디버깅 크롬 없음 — bash mac/launch_chrome.sh 후 로그인"
  warn "  (없어도 시세·유동주식수·대차잔고는 갱신되고 공매도만 직전 값 유지)"
fi

echo
echo "=== 배포 ==="
if command -v git >/dev/null 2>&1; then
  ok "git ($(git --version | awk '{print $3}'))"
  remote=$(git remote get-url origin 2>/dev/null || echo "")
  [[ -n "$remote" ]] && ok "origin: $remote" || bad "git remote origin 없음"
  if git push --dry-run -q origin main 2>/dev/null; then
    ok "푸시 권한 확인"
  else
    bad "푸시 불가 — gh auth login 또는 SSH 키 설정 필요"
  fi
else
  bad "git 없음 — xcode-select --install"
fi

echo
echo "=== 자동 실행 ==="
LABEL="com.shortdashboard.daily"
if launchctl print "gui/$(id -u)/$LABEL" >/dev/null 2>&1; then
  ok "launchd 등록됨 ($LABEL)"
else
  warn "미등록 — bash mac/install_schedule.sh"
fi

echo
if [[ $FAIL -eq 0 ]]; then
  printf "\033[32m문제 없음 — bash mac/daily.sh 로 1회 실행해보세요.\033[0m\n"
else
  printf "\033[31m%d건 해결 필요 (위의 ✗ 항목)\033[0m\n" "$FAIL"
fi
echo
exit 0
