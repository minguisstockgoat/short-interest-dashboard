#!/usr/bin/env bash
# ============================================================
#  자동 실행 등록 (launchd) — macOS
#
#    bash mac/install_schedule.sh              # 평일 22:00 + 아침 08:20
#    bash mac/install_schedule.sh 20 00        # 저녁만 20:00 으로
#    bash mac/install_schedule.sh 22 0 8 30    # 아침 시각까지 지정
#    bash mac/install_schedule.sh --uninstall
#
#  네 가지를 등록한다.
#    com.shortdashboard.daily     평일 지정 시각 1회 — 갱신 + 배포
#    com.shortdashboard.morning   평일 개장 전 1회 — 갓 공표된 전일 시세로 다시 그림
#    com.shortdashboard.keepalive 상주 — 5분마다 로그인 감지, 감지 즉시 갱신 실행
#    com.shortdashboard.agent     상주 — 대시보드 수동 갱신 버튼 수신
#
#  아침 실행이 따로 필요한 이유: KRX OpenAPI 는 당일 시세를 '다음날 아침 8시경'에
#  공표한다. 그래서 저녁 22:00 실행은 그날 시세를 못 받고, 기준일이 하루 전에
#  묶인다(build_dashboard 는 기준일을 prices.csv 에서 뽑는다). 확정 잔고는 이미
#  있는데 시세가 없어서 잘리는 것. 08:20 에 한 번 더 돌리면 개장 전에 D-1 추정까지
#  채워진다. 공표가 늦어지면 그날은 저녁과 같은 결과가 나올 뿐 손해는 없다.
#
#  launchd는 cron과 달리 맥이 잠들어 있던 시간대의 작업을 깨어난 직후 실행한다.
#  상주 작업(KeepAlive)은 죽으면 자동으로 다시 뜬다.
# ============================================================
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UID_="$(id -u)"
LA="$HOME/Library/LaunchAgents"

DAILY="com.shortdashboard.daily"
MORNING="com.shortdashboard.morning"
KEEP="com.shortdashboard.keepalive"
AGENT="com.shortdashboard.agent"

unload() {
  launchctl bootout "gui/$UID_/$1" 2>/dev/null || true
}

if [[ "${1:-}" == "--uninstall" ]]; then
  for l in "$DAILY" "$MORNING" "$KEEP" "$AGENT"; do
    unload "$l"
    rm -f "$LA/$l.plist"
  done
  echo "자동 실행 해제됨: $DAILY, $MORNING, $KEEP, $AGENT"
  exit 0
fi

HOUR="${1:-22}"
MIN="${2:-0}"
HOUR=$((10#$HOUR))
MIN=$((10#$MIN))

# 아침 실행 시각. 시세 공표(~08:00) 뒤, 개장(09:00) 전. 파이프라인 전체가 ~4분.
MHOUR="${3:-8}"
MMIN="${4:-20}"
MHOUR=$((10#$MHOUR))
MMIN=$((10#$MMIN))

mkdir -p "$LA" "$ROOT/logs"

# ---------------------------------------------------------------- 일일 갱신
cat > "$LA/$DAILY.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$DAILY</string>

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

# ---------------------------------------------------------------- 아침 갱신
cat > "$LA/$MORNING.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$MORNING</string>

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
      <key>Hour</key><integer>$MHOUR</integer>
      <key>Minute</key><integer>$MMIN</integer>
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

# ---------------------------------------------------------------- 세션 유지
cat > "$LA/$KEEP.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$KEEP</string>

  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>$ROOT/mac/keepalive.sh</string>
  </array>

  <key>WorkingDirectory</key><string>$ROOT</string>

  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>ThrottleInterval</key><integer>60</integer>

  <key>StandardOutPath</key><string>$ROOT/logs/keepalive.out.log</string>
  <key>StandardErrorPath</key><string>$ROOT/logs/keepalive.err.log</string>
  <key>ProcessType</key><string>Background</string>
</dict>
</plist>
EOF

# ---------------------------------------------------------------- 수동 갱신 에이전트
cat > "$LA/$AGENT.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$AGENT</string>

  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>$ROOT/mac/agent.sh</string>
  </array>

  <key>WorkingDirectory</key><string>$ROOT</string>

  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>ThrottleInterval</key><integer>30</integer>

  <key>StandardOutPath</key><string>$ROOT/logs/agent.out.log</string>
  <key>StandardErrorPath</key><string>$ROOT/logs/agent.err.log</string>
  <key>ProcessType</key><string>Background</string>
</dict>
</plist>
EOF

for l in "$DAILY" "$MORNING" "$KEEP" "$AGENT"; do
  unload "$l"
  launchctl bootstrap "gui/$UID_" "$LA/$l.plist"
done

cat <<MSG

  자동 실행 등록 완료
    일일 갱신 : $DAILY — 평일 $(printf '%02d:%02d' "$HOUR" "$MIN")
    아침 갱신 : $MORNING — 평일 $(printf '%02d:%02d' "$MHOUR" "$MMIN") (개장 전 D-1 추정 반영)
    로그인 감시 : $KEEP — 상주, 5분 주기 (로그인하면 그 자리에서 갱신)
    수동 갱신 : $AGENT — 상주, http://127.0.0.1:8776
    로그      : $ROOT/logs/

  즉시 실행 :  launchctl kickstart -k gui/$UID_/$DAILY
  상태 확인 :  launchctl print gui/$UID_/$KEEP | head -20
  해제      :  bash mac/install_schedule.sh --uninstall

  KRX 로그인은 네이버 SSO 라 사람이 한 번만 해주면 됩니다.
     bash mac/launch_chrome.sh   → 열린 창에서 네이버로 KRX 로그인
  이후 세션은 20분마다 자동 연장되고, 크롬을 껐다 켜도 프로필 쿠키로 복구됩니다.
  그래도 만료되면 텔레그램으로 "로그인 한 번만" 알림이 오고, 로그인하면 자동 복귀합니다.

MSG
