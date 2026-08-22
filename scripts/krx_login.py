# -*- coding: utf-8 -*-
"""KRX 로그인 세션 확보 (크롬 CDP) — KRX 자체 계정 자동 로그인.

  python scripts/krx_login.py            # 세션 확인, 없으면 자동 로그인
  python scripts/krx_login.py --open     # 로그인 창만 띄운다 (수동 로그인용)
  python scripts/krx_login.py --status   # 현재 세션/대기 상태만 출력
  python scripts/krx_login.py --reset    # 실패 누적·대기 상태 해제

**네이버 SSO 로는 자동화가 불가능하다.** KRX 는 네이버 OAuth 를
`auth_type=reauthenticate` 로 호출한다 — 프로필에 네이버 로그인 쿠키가 멀쩡히
살아 있어도 "세션 무시하고 비밀번호를 다시 받으라"는 뜻이라, 매번 사람이 네이버
비밀번호를 쳐야 한다. 세션이 30분 만에 죽는 것도 같은 정책이다.

그래서 **KRX 자체 계정**(마이페이지 > 정보수정에서 비밀번호 신규 설정)을 쓴다.
자체 로그인 폼은 캡차 없는 단순 POST 라 코드가 채워 넣을 수 있고, 네이버 계정을
전혀 건드리지 않으므로 계정 잠금 위험도 없다.

  KRX_ID / KRX_PW  — 중앙 볼트(~/.config/secrets/keys.env)에 둔다.

동작 순서
  1) 세션이 살아 있으면 그대로 쓴다.
  2) 크롬이 꺼져 있으면 띄워서 프로필 쿠키로 복구를 시도한다.
  3) 그래도 없으면 KRX_ID/KRX_PW 로 폼을 채워 자동 로그인한다.
  4) 자격증명이 없거나 연속 실패하면 자동 로그인을 끄고, 크롬 창을 로그인
     페이지로 띄운 뒤 텔레그램으로 알린다. 비밀번호 무한 재시도는 하지 않는다.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import time

import chrome
import notify
from common import DATA, log, require_primary

STATE = DATA / ".krx_login_state.json"
MAX_FAIL_STREAK = 2          # 이만큼 연속 실패하면 '수동 로그인 대기' 로 물러난다

# 자동 로그인이 이만큼 연속 실패하면 자격증명이 틀렸다고 보고 더 시도하지 않는다.
# KRX 도 실패가 쌓이면 계정을 잠그므로, 매일 같은 비밀번호로 두드리지 않는다.
MAX_NATIVE_FAIL = 2

# 크롬을 새로 띄운 직후 프로필 쿠키가 붙을 때까지 기다리는 횟수/간격
_REVIVE_TRIES = 3
_REVIVE_WAIT = 2.5

# 로그인 제출 후 세션이 붙을 때까지
_LOGIN_TRIES = 8
_LOGIN_WAIT = 2.0


# ---------------------------------------------------------------- 상태 파일
def load_state() -> dict:
    if STATE.exists():
        try:
            return json.loads(STATE.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            pass
    return {"fail_streak": 0, "locked": False, "last_ok": None,
            "last_fail": None, "last_reason": None,
            "native_fail": 0, "native_disabled": False}


def save_state(s: dict) -> None:
    STATE.write_text(json.dumps(s, ensure_ascii=False, indent=1), encoding="utf-8")


def _now() -> str:
    return dt.datetime.now().isoformat(timespec="seconds")


def record_ok(s: dict) -> None:
    s.update(fail_streak=0, locked=False, last_ok=_now(), last_reason=None,
             native_fail=0, native_disabled=False)
    save_state(s)
    notify.clear("krx-login-failed")
    notify.clear("krx-login-locked")
    notify.clear("krx-native-login-failed")


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
    """현재 크롬 쿠키로 로그인 상태인지.

    이 호출은 확인일 뿐 연장이 아니다. KRX 세션은 로그인 시각 기준 약 30분이면
    활동과 무관하게 끊긴다(2분 간격으로 인증 요청을 계속 보내며 실측했다).
    그래서 세션을 붙들어두려는 시도는 하지 않는다 — krx_keepalive 참고.
    """
    import krx_session
    try:
        s = krx_session.build_session(verify=False)
        ok, _ = krx_session.check_session(s)
        return ok
    except Exception:
        return False


# ---------------------------------------------------------------- 자동 로그인
# 로그인 폼은 top 문서가 아니라 iframe(login.jsp) 안에 있다.
_FILL_JS = """
(() => {
  const f = document.querySelector('iframe');
  if (!f || !f.contentDocument) return {err: 'iframe 없음'};
  const d = f.contentDocument;
  const id = d.querySelector('#mbrId') || d.querySelector('input[name=mbrId]');
  const pw = d.querySelector('input[name=pw]');
  if (!id || !pw) return {err: '입력란 없음 (이미 로그인 상태일 수 있음)'};
  const set = (el, v) => {
    el.focus();
    el.value = v;
    el.dispatchEvent(new Event('input',  {bubbles: true}));
    el.dispatchEvent(new Event('change', {bubbles: true}));
    el.dispatchEvent(new KeyboardEvent('keyup', {bubbles: true}));
  };
  set(id, %s);
  set(pw, %s);
  const btn = [...d.querySelectorAll('a,button,input[type=submit]')]
    .find(x => (x.innerText || x.value || '').trim() === '로그인');
  if (!btn) return {err: '로그인 버튼 없음'};
  btn.click();
  return {submitted: true};
})()
"""

# 이전 세션이 서버에 남아 있으면 "이미 로그인된 계정입니다. 기존 계정을 로그아웃하고
# 새로 로그인하시겠습니까?" jQuery UI 다이얼로그가 뜨고 거기서 멈춘다.
# 우리 계정의 낡은 세션이므로 '확인'을 눌러 밀어낸다.
_CONFIRM_JS = """
(() => {
  const f = document.querySelector('iframe');
  if (!f || !f.contentDocument) return {found: false};
  const d = f.contentDocument;
  const vis = el => { const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
  const asked = [...d.querySelectorAll('div,section,p,span')]
    .some(e => vis(e) && (e.innerText || '').includes('이미 로그인된 계정입니다'));
  if (!asked) return {found: false};
  const ok = [...d.querySelectorAll('button,a')]
    .find(e => vis(e) && (e.innerText || '').trim() === '확인');
  if (!ok) return {found: true, clicked: false};
  ok.click();
  return {found: true, clicked: true};
})()
"""


def credentials() -> tuple[str, str] | None:
    """볼트/.env 에서 KRX 자체 계정 자격증명. 없으면 None."""
    uid, pw = os.environ.get("KRX_ID"), os.environ.get("KRX_PW")
    return (uid, pw) if uid and pw else None


def native_login(state: dict) -> bool:
    """KRX 자체 계정으로 로그인한다. 성공하면 True.

    비밀번호는 로그·예외 어디에도 남기지 않는다. 실패해도 이 함수 안에서
    재시도하지 않는다 — 실패가 쌓이면 KRX 가 계정을 잠그기 때문이다.
    """
    cred = credentials()
    if not cred:
        log("KRX_ID/KRX_PW 가 없어 자동 로그인을 건너뜁니다 "
            "(볼트: ~/.config/secrets/keys.env)")
        return False
    if state.get("native_disabled"):
        log(f"자동 로그인 비활성 상태 (연속 {state.get('native_fail')}회 실패) "
            "— 자격증명 확인 후 krx_login.py --reset")
        return False

    if not chrome.cdp_up() and not chrome.launch():
        log("크롬을 띄우지 못해 자동 로그인을 못 했습니다.")
        return False

    from cdp import open_page

    log("KRX 자체 계정으로 자동 로그인 시도")
    try:
        with open_page("krx.co.kr") as page:
            page.navigate(chrome.LOGIN_URL, settle=4.0)
            page.wait_ready(timeout=25)
            res = page.evaluate(_FILL_JS % (json.dumps(cred[0]), json.dumps(cred[1])))
            if isinstance(res, dict) and res.get("err"):
                log(f"자동 로그인 폼 처리 실패: {res['err']}")
                return False

            # 제출 후 세션이 붙기까지 잠깐 걸린다. 그 사이 "이미 로그인된 계정"
            # 확인창이 뜨면 눌러준다. 페이지가 넘어가면 CDP 평가가 실패하는데,
            # 그건 로그인이 진행됐다는 뜻이므로 무시하고 세션만 계속 본다.
            confirmed = False
            for _ in range(_LOGIN_TRIES):
                time.sleep(_LOGIN_WAIT)
                if session_alive():
                    log("✅ 자동 로그인 성공")
                    return True
                if confirmed:
                    continue
                try:
                    c = page.evaluate(_CONFIRM_JS)
                except Exception:
                    continue
                if isinstance(c, dict) and c.get("clicked"):
                    log("기존 세션이 남아 있어 '확인'으로 밀어냈습니다")
                    confirmed = True
    except Exception as e:
        # 예외 메시지에 폼 내용이 실릴 수 있으므로 타입만 남긴다.
        log(f"자동 로그인 중 오류: {type(e).__name__}")
        return False

    log("자동 로그인 후에도 세션이 확인되지 않습니다 (비밀번호 변경/잠금 가능)")
    return False


def record_native_fail(s: dict) -> None:
    """자동 로그인 실패를 세고, 임계치를 넘으면 아예 꺼서 계정을 지킨다."""
    s["native_fail"] = int(s.get("native_fail", 0)) + 1
    if s["native_fail"] >= MAX_NATIVE_FAIL and not s.get("native_disabled"):
        s["native_disabled"] = True
        save_state(s)
        notify.send(
            f"🔒 KRX 자동 로그인이 {s['native_fail']}회 연속 실패해 껐습니다.\n"
            "계정 잠금을 피하려고 더는 시도하지 않습니다.\n\n"
            "볼트(~/.config/secrets/keys.env)의 KRX_ID / KRX_PW 를 확인하고,\n"
            "고친 뒤 아래로 다시 켜주세요.\n"
            "  cd ~/short-dashboard && .venv/bin/python scripts/krx_login.py --reset",
            dedupe="krx-native-login-failed", cooldown_h=24)
    else:
        save_state(s)


def open_login_window() -> bool:
    """사람이 로그인할 KRX 화면을 띄운다.

    크롬이 떠 있어도 창을 다 닫았거나 빈 새 탭만 있으면 로그인할 화면이 없다.
    KRX 탭이 실제로 있는지까지 보고, 없으면 로그인 페이지를 연다.
    """
    if not chrome.cdp_up():
        return chrome.launch()

    try:
        pages = [t for t in chrome.targets() if t.get("type") == "page"]
    except Exception:
        pages = []

    # KRX 탭이 있어도 로그인 화면이 떠 있다는 보장은 없다(세션 연장으로 데이터
    # 페이지에 가 있는 게 보통이다). 사람이 로그인하려고 부른 명령이므로,
    # 있으면 그 탭을 로그인 페이지로 보내고 없으면 새로 연다.
    if any("krx.co.kr" in (p.get("url") or "") for p in pages):
        from cdp import open_page
        try:
            with open_page("krx.co.kr") as page:
                page.navigate(chrome.LOGIN_URL, settle=2.0)
            log("KRX 탭을 로그인 페이지로 이동했습니다.")
            return True
        except Exception as e:
            log(f"기존 탭 이동 실패({type(e).__name__}) — 새 탭을 엽니다.")
    return chrome.new_tab()


def ensure_login(*, force: bool = False) -> bool:
    """수집이 쓸 세션을 확보한다. 사람의 로그인이 필요하면 알리고 False.

    보통은 KRX 자체 계정으로 스스로 로그인해서 True 를 돌려준다. 자격증명이
    없거나 자동 로그인이 연속 실패한 경우에만 사람을 부른다.
    """
    # 담당 머신이 아니면 로그인 자체를 시도하지 않는다. 다른 PC 를 켤 때마다
    # KRX 로그인 요청이 뜨던 원인이 여기였다.
    if not require_primary("KRX 로그인"):
        return False

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

    # 세션이 없다 → KRX 자체 계정으로 스스로 로그인한다.
    if native_login(st):
        record_ok(st)
        return True
    if credentials() and not st.get("native_disabled"):
        record_native_fail(st)

    if st.get("locked"):
        log(f"수동 로그인 대기 중 (연속 {st.get('fail_streak')}회 실패, "
            f"마지막 사유: {st.get('last_reason')})")
        log("  크롬 창에서 로그인하면 자동 복구됩니다. "
            "상태 초기화는 krx_login.py --reset")
        notify.send(
            "KRX 세션이 아직 없어 이번 갱신에서도 공매도를 건너뜁니다.\n"
            "KRX 전용 크롬 창에서 로그인만 해주시면 바로 재개됩니다.",
            dedupe="krx-login-locked", cooldown_h=24)
        return False

    # 자동 로그인도 안 됐고 세션도 없다 = 사람이 로그인해줘야 한다
    reason = ("자동 로그인 실패 — 자격증명 확인 필요" if credentials()
              else "세션 만료 — KRX_ID/KRX_PW 미설정, 수동 로그인 필요")
    record_fail(st, reason)
    return False


# ---------------------------------------------------------------- CLI
def main() -> int:
    ap = argparse.ArgumentParser(
        description="KRX 로그인 세션 확보 (KRX 자체 계정 자동 로그인)")
    ap.add_argument("--force", action="store_true", help="세션이 살아 있어도 다시 점검")
    ap.add_argument("--open", action="store_true",
                    help="로그인 페이지를 띄운 크롬만 준비 (수동 로그인용)")
    ap.add_argument("--status", action="store_true", help="상태만 출력")
    ap.add_argument("--reset", action="store_true",
                    help="실패 누적·대기 상태 해제 (자동 로그인도 다시 켠다)")
    a = ap.parse_args()

    if not (a.status or a.reset) and not require_primary("KRX 로그인"):
        return 1

    if a.reset:
        s = load_state()
        s.update(fail_streak=0, locked=False, last_reason=None,
                 native_fail=0, native_disabled=False)
        save_state(s)
        notify.clear("krx-login-failed")
        notify.clear("krx-login-locked")
        notify.clear("krx-native-login-failed")
        print("✅ 대기 상태 해제. 다음 실행에서 세션을 다시 확인합니다.")
        return 0

    if a.open:
        ok = open_login_window()
        if ok:
            print("✅ 크롬 준비됨 — 열린 창에서 KRX 로그인해 주세요.")
            print("   로그인 후 확인:  .venv/bin/python scripts/krx_login.py --status")
        else:
            print("❌ 크롬을 띄우지 못했습니다.")
        return 0 if ok else 1

    if a.status:
        s = load_state()
        alive = session_alive()
        waiting = "대기 중 — 크롬 창에서 로그인 필요" if s.get("locked") else "불필요"
        auto = ("꺼짐 — 자격증명 확인 후 --reset" if s.get("native_disabled")
                else ("사용 가능" if credentials() else "KRX_ID/KRX_PW 없음"))
        print(f"세션      : {'유효' if alive else '없음/만료'}")
        print(f"자동 로그인: {auto} (실패 {s.get('native_fail', 0)}/{MAX_NATIVE_FAIL})")
        print(f"연속 실패 : {s.get('fail_streak', 0)} / {MAX_FAIL_STREAK}")
        print(f"수동로그인 : {waiting}")
        print(f"마지막 성공: {s.get('last_ok') or '-'}")
        print(f"마지막 실패: {s.get('last_fail') or '-'} {s.get('last_reason') or ''}")
        return 0 if alive else 1

    ok = ensure_login(force=a.force)
    print("\n✅ KRX 로그인 세션 사용 가능" if ok
          else "\n❌ 세션 없음 — 자격증명 확인 또는 크롬 창에서 수동 로그인이 필요합니다")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
