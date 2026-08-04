# -*- coding: utf-8 -*-
"""KRX 로그인 세션 상시 유지 (맥미니 상주 프로세스).

  python scripts/krx_keepalive.py                 # 30분 주기
  python scripts/krx_keepalive.py --interval 900  # 15분 주기
  python scripts/krx_keepalive.py --once          # 한 번만 점검하고 종료

30분마다 가벼운 조회를 한 번 던져 JSESSIONID 를 연장한다. 세션이 끊겼으면
krx_login 으로 재로그인을 위임한다(시도 횟수 제한은 그쪽이 들고 있다).

잠금 상태에 들어가면 주기를 늘려 조용히 대기한다 — 사람이 --reset 하기 전까지
KRX를 두드려봐야 계정 잠금 위험만 키우기 때문이다.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import signal
import sys
import time

import chrome
import krx_login
import notify
from common import DATA, log

HEARTBEAT = DATA / ".keepalive.json"
DEFAULT_INTERVAL = 1800          # 30분
LOCKED_INTERVAL = 3600           # 잠금 중에는 1시간마다 상태만 확인

_stop = False


def _on_signal(signum, _frame):
    global _stop
    _stop = True
    log(f"종료 신호({signum}) 수신 — 정리 후 종료합니다.")


def beat(status: str, detail: str = "") -> None:
    """마지막 점검 결과를 남긴다(대시보드 에이전트가 읽어 상태를 보여준다)."""
    try:
        HEARTBEAT.write_text(json.dumps({
            "at": dt.datetime.now().isoformat(timespec="seconds"),
            "status": status,
            "detail": detail,
        }, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass


def tick() -> str:
    """한 번 점검한다. 'ok' | 'relogin' | 'locked' | 'failed'"""
    st = krx_login.load_state()

    if krx_login.session_alive():
        if st.get("fail_streak"):
            krx_login.record_ok(st)
        beat("ok", "세션 연장됨")
        return "ok"

    if st.get("locked"):
        beat("locked", st.get("last_reason") or "자동 로그인 잠금")
        log("세션 없음 + 자동 로그인 잠금 — 재시도하지 않고 대기")
        return "locked"

    log("세션이 끊겼습니다 — 재로그인 시도")
    if not chrome.cdp_up() and not chrome.launch():
        beat("failed", "크롬 기동 실패")
        return "failed"

    if krx_login.ensure_login():
        beat("relogin", "재로그인 성공")
        notify.send("✅ KRX 세션이 끊겨 자동 재로그인했습니다. 정상 동작 중입니다.",
                    dedupe="krx-relogin", cooldown_h=24)
        return "relogin"

    beat("failed", krx_login.load_state().get("last_reason") or "재로그인 실패")
    return "failed"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--interval", type=int, default=DEFAULT_INTERVAL,
                    help=f"점검 주기(초), 기본 {DEFAULT_INTERVAL}")
    ap.add_argument("--once", action="store_true", help="한 번만 점검")
    a = ap.parse_args()

    signal.signal(signal.SIGTERM, _on_signal)
    signal.signal(signal.SIGINT, _on_signal)

    if a.once:
        r = tick()
        print(f"결과: {r}")
        return 0 if r in ("ok", "relogin") else 1

    log(f"KRX 세션 유지 시작 — {a.interval}초 주기")
    while not _stop:
        try:
            result = tick()
        except Exception as e:                   # 상주 프로세스는 어떤 예외로도 죽지 않는다
            log(f"점검 중 예외: {type(e).__name__} {e}")
            beat("error", f"{type(e).__name__}: {e}")
            result = "failed"

        wait = LOCKED_INTERVAL if result == "locked" else a.interval
        # 종료 신호에 빠르게 반응하도록 잘게 나눠 잔다
        slept = 0.0
        while slept < wait and not _stop:
            time.sleep(min(5.0, wait - slept))
            slept += 5.0

    log("KRX 세션 유지 종료")
    return 0


if __name__ == "__main__":
    sys.exit(main())
