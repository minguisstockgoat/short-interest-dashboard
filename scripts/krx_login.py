# -*- coding: utf-8 -*-
"""KRX 로그인 세션 확보 (크롬 CDP) — 네이버 SSO 수동 로그인 기반.

  python scripts/krx_login.py            # 세션 확인, 없으면 크롬 띄우고 안내
  python scripts/krx_login.py --open     # 로그인 창만 띄운다 (사람이 로그인할 때)
  python scripts/krx_login.py --status   # 현재 세션/대기 상태만 출력
  python scripts/krx_login.py --reset    # 실패 누적·대기 상태 해제

KRX 로그인은 네이버 계정 SSO 라서 아이디/비밀번호를 코드가 대신 넣을 수 없다
(네이버가 캡차·기기등록·2단계인증을 걸기 때문에 자동 입력은 실패하거나 계정을
위험 상태로 만든다). 그래서 이 스크립트는 비밀번호를 다루지 않는다.

대신 전용 크롬 프로필(`.chrome-profile`)에 남는 쿠키를 세션의 근거로 쓴다.

  1) 사람이 그 프로필의 크롬 창에서 네이버로 KRX 로그인을 **한 번** 한다.
  2) 쿠키가 프로필 디스크에 남으므로, 크롬을 껐다 켜도 로그인이 유지된다.
  3) krx_keepalive 가 주기적으로 가벼운 조회를 던져 세션을 연장한다.
  4) 그래도 만료되면 이 스크립트가 크롬 창을 로그인 페이지로 띄우고
     텔레그램으로 "다시 로그인해 달라"고 알린다. 무한 재시도는 하지 않는다.

즉 자동화가 스스로 못 하는 건 딱 하나 — 사람의 최초/재로그인뿐이다.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import time

import chrome
import notify
from common import DATA, log

STATE = DATA / ".krx_login_state.json"
MAX_FAIL_STREAK = 2          # 이만큼 연속 실패하면 '수동 로그인 대기' 로 물러난다

# 크롬을 새로 띄운 직후 프로필 쿠키가 붙을 때까지 기다리는 횟수/간격
_REVIVE_TRIES = 3
_REVIVE_WAIT = 2.5


# ---------------------------------------------------------------- 상태 파일
def load_state() -> dict:
    if STATE.exists():
        try:
            return json.loads(STATE.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            pass
    return {"fail_streak": 0, "locked": False, "last_ok": None,
            "last_fail": None, "last_reason": None}


def save_state(s: dict) -> None:
    STATE.write_text(json.dumps(s, ensure_ascii=False, indent=1), encoding="utf-8")


def _now() -> str:
    return dt.datetime.now().isoformat(timespec="seconds")


def record_ok(s: dict) -> None:
    s.update(fail_streak=0, locked=False, last_ok=_now(), last_reason=None)
    save_state(s)
    notify.clear("krx-login-failed")
    notify.clear("krx-login-locked")


def record_fail(s: dict, reason: str) -> bool:
    """실패를 기록하고, 수동 로그인 대기 상태로 들어갔으면 True."""
    s["fail_streak"] = int(s.get("fail_streak", 0)) + 1
    s["last_fail"] = _now()
    s["last_reason"] = reason
    newly_locked = False
    if s["fail_streak"] >= MAX_FAIL_STREAK and not s.get("locked"):
        s["locked"] = True
        newly_locked = True
    save_state(s)

    log(f"세션 확보 실패({s['fail_streak']}/{MAX_FAIL_STREAK}): {reason}")
    if newly_locked:
        notify.send(
            f"🔑 KRX 로그인 세션이 만료됐습니다 — 네이버 로그인 한 번만 부탁드립니다.\n"
            f"사유: {reason}\n\n"
            f"맥에 떠 있는 KRX 전용 크롬 창에서 네이버로 로그인해 주세요.\n"
            f"창이 없으면 아래를 실행하면 로그인 페이지로 열립니다.\n"
            f"  cd ~/short-dashboard && bash mac/launch_chrome.sh\n\n"
            f"로그인만 하면 이후 갱신은 자동으로 재개됩니다. "
            f"공매도 숫자는 그때까지 직전 값으로 유지됩니다.",
            dedupe="krx-login-failed", cooldown_h=12)
    return newly_locked


# ---------------------------------------------------------------- 세션
def session_alive() -> bool:
    """현재 크롬 쿠키로 로그인 상태인지."""
    import krx_session
    try:
        s = krx_session.build_session(verify=False)
        ok, _ = krx_session.check_session(s)
        return ok
    except Exception:
        return False


def open_login_window() -> bool:
    """로그인 페이지를 띄운 전용 프로필 크롬을 준비한다.

    크롬이 떠 있어도 창을 다 닫았으면 사람이 로그인할 화면이 없다 — 탭을 연다.
    """
    if chrome.cdp_up():
        return chrome.ensure_page()
    return chrome.launch()


def ensure_login(*, force: bool = False) -> bool:
    """수집이 쓸 세션을 확보한다. 사람의 로그인이 필요하면 알리고 False.

    비밀번호를 넣지 않으므로 계정 잠금 위험은 없다. 대신 사람이 로그인해줄
    때까지 조용히 기다리는 게 이 함수의 정상 동작이다.
    """
    st = load_state()

    if not force and session_alive():
        log("KRX 세션 이미 유효 — 로그인 불필요")
        if st.get("fail_streak") or st.get("locked"):
            record_ok(st)
        return True

    # 크롬이 꺼져 있으면 쿠키가 멀쩡해도 session_alive() 는 False 다(CDP로 읽으므로).
    # 띄워보면 프로필에 남은 쿠키로 그대로 되살아나는 경우가 대부분이다.
    if not chrome.cdp_up():
        log("크롬이 떠 있지 않습니다 — 프로필 쿠키로 세션 복구를 시도합니다.")
        if not chrome.launch():
            log("크롬을 띄우지 못했습니다.")
            notify.send(
                "맥에서 크롬(원격 디버깅 9222)을 띄우지 못했습니다.\n"
                "화면 잠금/자동 로그인 설정을 확인해 주세요.",
                dedupe="chrome-launch-failed", cooldown_h=12)
            return False

        for _ in range(_REVIVE_TRIES):
            time.sleep(_REVIVE_WAIT)
            if session_alive():
                log("✅ 프로필 쿠키로 세션 복구됨 — 재로그인 불필요")
                record_ok(st)
                return True

    if st.get("locked"):
        log(f"수동 로그인 대기 중 (연속 {st.get('fail_streak')}회 실패, "
            f"마지막 사유: {st.get('last_reason')})")
        log("  크롬 창에서 네이버 로그인하면 자동 복구됩니다. "
            "상태 초기화는 krx_login.py --reset")
        notify.send(
            "KRX 세션이 아직 없어 이번 갱신에서도 공매도를 건너뜁니다.\n"
            "KRX 전용 크롬 창에서 네이버 로그인만 해주시면 바로 재개됩니다.",
            dedupe="krx-login-locked", cooldown_h=24)
        return False

    # 크롬은 떠 있는데 세션이 없다 = 사람이 로그인해줘야 한다
    record_fail(st, "세션 만료 — 네이버 SSO 수동 로그인 필요")
    return False


# ---------------------------------------------------------------- CLI
def main() -> int:
    ap = argparse.ArgumentParser(
        description="KRX 로그인 세션 확보 (네이버 SSO 수동 로그인)")
    ap.add_argument("--force", action="store_true", help="세션이 살아 있어도 다시 점검")
    ap.add_argument("--open", action="store_true",
                    help="로그인 페이지를 띄운 크롬만 준비 (사람이 로그인할 때)")
    ap.add_argument("--status", action="store_true", help="상태만 출력")
    ap.add_argument("--reset", action="store_true", help="실패 누적·대기 상태 해제")
    a = ap.parse_args()

    if a.reset:
        s = load_state()
        s.update(fail_streak=0, locked=False, last_reason=None)
        save_state(s)
        notify.clear("krx-login-failed")
        notify.clear("krx-login-locked")
        print("✅ 대기 상태 해제. 다음 실행에서 세션을 다시 확인합니다.")
        return 0

    if a.open:
        ok = open_login_window()
        if ok:
            print("✅ 크롬 준비됨 — 열린 창에서 네이버로 KRX 로그인해 주세요.")
            print("   로그인 후 확인:  .venv/bin/python scripts/krx_login.py --status")
        else:
            print("❌ 크롬을 띄우지 못했습니다.")
        return 0 if ok else 1

    if a.status:
        s = load_state()
        alive = session_alive()
        waiting = "대기 중 — 크롬 창에서 네이버 로그인 필요" if s.get("locked") else "불필요"
        print(f"세션      : {'유효' if alive else '없음/만료'}")
        print(f"연속 실패 : {s.get('fail_streak', 0)} / {MAX_FAIL_STREAK}")
        print(f"수동로그인 : {waiting}")
        print(f"마지막 성공: {s.get('last_ok') or '-'}")
        print(f"마지막 실패: {s.get('last_fail') or '-'} {s.get('last_reason') or ''}")
        return 0 if alive else 1

    ok = ensure_login(force=a.force)
    print("\n✅ KRX 로그인 세션 사용 가능" if ok
          else "\n❌ 세션 없음 — 크롬 창에서 네이버 로그인이 필요합니다")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
