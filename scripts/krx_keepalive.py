# -*- coding: utf-8 -*-
"""KRX 로그인 세션 상시 유지 (맥미니 상주 프로세스).

  python scripts/krx_keepalive.py                 # 30분 주기
  python scripts/krx_keepalive.py --interval 900  # 15분 주기
  python scripts/krx_keepalive.py --once          # 한 번만 점검하고 종료

30분마다 가벼운 조회를 한 번 던져 JSESSIONID 를 연장한다. 세션이 끊겼으면
krx_login 에 복구를 위임한다(크롬 기동·프로필 쿠키 복구는 그쪽이 들고 있다).

복구가 안 돼 수동 로그인 대기로 넘어가면 주기를 늘려 조용히 기다린다 —
사람이 크롬 창에서 네이버 로그인을 해줘야 풀리는 상황이라, 그 전까지 KRX를
계속 두드려봐야 의미가 없기 때문이다. 로그인되면 다음 점검에서 자동 복귀한다.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import signal
import sys
import time

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
        if st.get("fail_streak") or st.get("locked"):
            krx_login.record_ok(st)
        beat("ok", "세션 연장됨")
        return "ok"

    # 대기 상태여도 먼저 ensure_login 에 넘긴다 — 크롬이 꺼져 있으면 session_alive()
    # 는 쿠키가 멀쩡해도 False 라서, 띄워봐야 복구 가능 여부를 알 수 있다.
    was_waiting = bool(st.get("locked"))
    log("세션이 끊겼습니다 — 프로필 쿠키로 복구 시도")
    if krx_login.ensure_login():
        beat("relogin", "세션 복구됨")
        if was_waiting:
            notify.send("✅ KRX 세션이 복구됐습니다. 정상 동작 중입니다.",
                        dedupe="krx-relogin", cooldown_h=24)
        return "relogin"

    st = krx_login.load_state()
    if st.get("locked"):
        beat("locked", st.get("last_reason") or "수동 로그인 대기")
        log("네이버 수동 로그인 대기 — 더 시도하지 않고 기다립니다")
        return "locked"

    beat("failed", st.get("last_reason") or "세션 복구 실패")
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
