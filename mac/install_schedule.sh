#!/usr/bin/env bash
# ============================================================
#  매일 자동 갱신 등록 (launchd) — macOS
#
#    bash mac/install_schedule.sh              # 평일 18:30
#    bash mac/install_schedule.sh 20 00        # 평일 20:00
#    bash mac/install_schedule.sh --uninstall
#
#  launchd는 cron과 달리 맥이 잠들어 있어도 깨어난 직후 놓친 작업을 실행한다.
# ============================================================
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LABEL="com.shortdashboard.daily"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"

if [[ "${1:-}" == "--uninstall" ]]; then
  launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
  rm -f "$PLIST"
  echo "자동 실행 해제됨: $LABEL"
  exit 0
fi

HOUR="${1:-18}"
MIN="${2:-30}"

mkdir -p "$HOME/Library/LaunchAgents" "$ROOT/logs"

# 평일(월~금) = Weekday 1..5
cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL</string>

  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>$ROOT/mac/daily.sh</string>
  </array>

  <key>WorkingDirectory</key><string>$ROOT</string>

  <key>StartCalendarInterval</key>
  <array>
$(for d in 1 2 3 4 5; do
cat <<ENTRY
    <dict>
      <key>Weekday</key><integer>$d</integer>
      <key>Hour</key><integer>$HOUR</integer>
      <key>Minute</key><integer>$MIN</integer>
    </dict>
ENTRY
done)
  </array>

  <key>StandardOutPath</key><string>$ROOT/logs/launchd.out.log</string>
  <key>StandardErrorPath</key><string>$ROOT/logs/launchd.err.log</string>

  <key>RunAtLoad</key><false/>
  <key>ProcessType</key><string>Background</string>
</dict>
</plist>
EOF

launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"

echo
echo "  자동 실행 등록 완료"
echo "    라벨   : $LABEL"
echo "    시각   : 평일 $(printf '%02d:%02d' "$HOUR" "$MIN")"
echo "    plist  : $PLIST"
echo "    로그   : $ROOT/logs/"
echo
echo "  즉시 실행:  launchctl kickstart -k gui/$(id -u)/$LABEL"
echo "  상태 확인:  launchctl print gui/$(id -u)/$LABEL | head -20"
echo "  해제     :  bash mac/install_schedule.sh --uninstall"
echo
echo "  참고: KRX 공매도는 크롬 로그인 세션이 필요합니다."
echo "        mac/launch_chrome.sh 로 띄운 크롬을 로그인 상태로 두세요."
echo "        세션이 없으면 나머지만 갱신되고 공매도는 직전 값이 유지됩니다."
echo
