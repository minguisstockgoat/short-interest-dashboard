# -*- coding: utf-8 -*-
"""KRX 로그인 감시 — 사람이 로그인하면 그 순간 갱신을 돌린다 (상주 프로세스).

  python scripts/krx_keepalive.py            # 5분 주기 감시
  python scripts/krx_keepalive.py --once     # 한 번만 점검하고 종료
  python scripts/krx_keepalive.py --no-run   # 감지만 하고 파이프라인은 안 돌림

KRX 세션은 **로그인 후 약 30분**이면 활동과 무관하게 끊긴다. 2분 간격으로 인증
요청을 계속 보내면서 재봤는데도 정확히 30분에 만료됐다 — 연장으로는 못 버틴다.

예전에는 네이버 SSO 뿐이라 사람이 하루 한 번 로그인해줘야 했지만, 지금은 KRX
자체 계정으로 코드가 직접 로그인한다(krx_login.native_login). 그래서 이 프로세스는
5분마다 세션을 보다가,

  · 세션이 없으면 스스로 로그인하고
  · 오늘 아직 갱신이 안 돌았으면

곧바로 파이프라인을 돌린다. 사람이 할 일은 없다. 자동 로그인이 연속 실패해서
꺼진 경우에만(자격증명 문제) 정해진 시각 이후 한 번 알린다.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import signal
import subprocess
import sys
import time
from pathlib import Path

import krx_login
import notify
from common import DATA, ROOT, log

HEARTBEAT = DATA / ".keepalive.json"
WATCH_STATE = DATA / ".watch_state.json"

# KRX 세션 수명(관측값). 로그인 시각 기준이며 활동해도 늘지 않는다.
SESSION_LIFETIME = 1800          # 약 30분
DEFAULT_INTERVAL = 300           # 5분 — 로그인을 빨리 알아채는 게 유일한 목적

REMIND_HOUR = 21                 # 이 시각까지 갱신이 없으면 로그인 요청 알림

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


def load_watch() -> dict:
    if WATCH_STATE.exists():
        try:
            return json.loads(WATCH_STATE.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            pass
    return {"last_run_date": None, "last_run_at": None, "last_exit": None}


def save_watch(s: dict) -> None:
    try:
        WATCH_STATE.write_text(json.dumps(s, ensure_ascii=False, indent=1),
                               encoding="utf-8")
    except OSError:
        pass


def ran_today(w: dict) -> bool:
    return w.get("last_run_date") == dt.date.today().strftime("%Y%m%d")


def run_pipeline() -> int:
    """로그인이 감지된 김에 갱신을 끝까지 돌린다.

    세션 수명이 30분이라 지체할 여유가 없다 — 감지 즉시 시작한다.
    """
    py = sys.executable
    cmd = [py, str(Path(ROOT) / "scripts" / "pipeline.py"),
           "--days", "10", "--deploy", "--source", "login"]
    log("로그인 감지 — 갱신을 시작합니다: " + " ".join(cmd[-6:]))
    p = subprocess.run(cmd, cwd=str(ROOT))
    log(f"갱신 종료 (exit={p.returncode})")
    return p.returncode


def tick(*, allow_run: bool = True) -> str:
    """한 번 점검한다. 'ran' | 'ok' | 'waiting' | 'failed'"""
    st = krx_login.load_state()
    w = load_watch()

    # 세션이 없으면 스스로 로그인한다(KRX 자체 계정). 크롬이 꺼져 있으면 띄워서
    # 프로필 쿠키로 살아나는지도 ensure_login 안에서 본다. 여기서 성공하면
    # 다음 tick 을 기다리지 않고 이번 차례에 바로 갱신까지 간다.
    alive = krx_login.session_alive() or krx_login.ensure_login()

    if alive:
        if st.get("fail_streak") or st.get("locked"):
            krx_login.record_ok(st)

        if ran_today(w):
            beat("ok", "세션 유효 · 오늘 갱신 완료")
            return "ok"

        if not allow_run:
            beat("ok", "세션 유효 · 갱신 대기(--no-run)")
            return "ok"

        code = run_pipeline()
        w.update(last_run_date=dt.date.today().strftime("%Y%m%d"),
                 last_run_at=dt.datetime.now().isoformat(timespec="seconds"),
                 last_exit=code)
        save_watch(w)
        if code == 0:
            beat("ok", "로그인 감지 → 갱신 완료")
            notify.send("✅ 로그인 감지 — 공매도 갱신을 끝냈습니다. "
                        "오늘은 더 로그인하지 않으셔도 됩니다.",
                        dedupe="daily-update-done", cooldown_h=12)
            return "ran"
        beat("failed", f"갱신 실패 (exit={code})")
        notify.send(f"❌ 로그인은 됐는데 갱신이 실패했습니다 (exit={code}).\n"
                    f"logs/pipeline_*.log 를 확인해 주세요.",
                    dedupe="daily-update-failed", cooldown_h=6)
        return "failed"

    # 자동 로그인까지 실패했다 = 자격증명이 틀렸거나 KRX 쪽 문제다.
    if not ran_today(w) and dt.datetime.now().hour >= REMIND_HOUR:
        notify.send(
            "🔑 오늘 공매도 갱신이 아직입니다 — 자동 로그인이 안 되고 있습니다.\n"
            "볼트의 KRX_ID / KRX_PW 를 확인하거나, KRX 전용 크롬 창에서 "
            "직접 로그인해 주세요.\n"
            "로그인되면 5분 안에 자동으로 갱신이 돌고 배포까지 끝납니다.",
            dedupe="daily-login-request", cooldown_h=20)

    beat("waiting", "로그인 대기 중" + ("" if not ran_today(w) else " · 오늘 갱신은 완료"))
    return "waiting"


def main() -> int:
    ap = argparse.ArgumentParser(
        description="KRX 로그인 감시 — 로그인하면 그 자리에서 갱신을 돌린다")
    ap.add_argument("--interval", type=int, default=DEFAULT_INTERVAL,
                    help=f"점검 주기(초), 기본 {DEFAULT_INTERVAL}")
    ap.add_argument("--once", action="store_true", help="한 번만 점검")
    ap.add_argument("--no-run", action="store_true",
                    help="로그인을 감지해도 파이프라인은 돌리지 않는다")
    a = ap.parse_args()

    signal.signal(signal.SIGTERM, _on_signal)
    signal.signal(signal.SIGINT, _on_signal)

    if a.once:
        r = tick(allow_run=not a.no_run)
        print(f"결과: {r}")
        return 0 if r in ("ok", "ran") else 1

    log(f"KRX 로그인 감시 시작 — {a.interval}초 주기 "
        f"(세션 수명 {SESSION_LIFETIME // 60}분, 연장 불가)")
    while not _stop:
        try:
            tick(allow_run=not a.no_run)
        except Exception as e:                   # 상주 프로세스는 어떤 예외로도 죽지 않는다
            log(f"점검 중 예외: {type(e).__name__} {e}")
            beat("error", f"{type(e).__name__}: {e}")

        slept = 0.0
        while slept < a.interval and not _stop:   # 종료 신호에 빠르게 반응
            time.sleep(min(5.0, a.interval - slept))
            slept += 5.0

    log("KRX 로그인 감시 종료")
    return 0


if __name__ == "__main__":
    sys.exit(main())
