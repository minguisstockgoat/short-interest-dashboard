# -*- coding: utf-8 -*-
"""KRX 자동 로그인 (크롬 CDP).

  python scripts/krx_login.py            # 필요하면 로그인
  python scripts/krx_login.py --force    # 이미 로그인돼 있어도 다시
  python scripts/krx_login.py --dry-run  # 입력만 하고 제출은 안 함 (첫 점검용)
  python scripts/krx_login.py --status   # 현재 세션/잠금 상태만 출력
  python scripts/krx_login.py --reset    # 실패 누적·잠금 해제

계정은 .env 에서 읽는다.

    KRX_ID=아이디
    KRX_PW=비밀번호

⚠ KRX는 로그인 5회 실패 시 계정을 잠근다. 그래서 이 스크립트는
  - 한 번 호출에 로그인 시도를 **1회만** 하고,
  - 연속 2회 실패하면 스스로 **잠금 모드**로 들어가 더 시도하지 않으며,
  - 텔레그램으로 알리고 사람이 `--reset` 할 때까지 기다린다.
무한 재시도로 계정이 잠기는 상황을 코드 차원에서 막는 게 목적이다.

로그인 폼은 JS로 그려지므로 셀렉터를 박아두지 않고 런타임에 DOM에서
비밀번호 칸을 찾아 그 앞의 입력칸을 아이디로 본다. KRX가 화면을 바꿔도
버티도록 한 것이고, 무엇을 찾았는지는 로그에 남긴다.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import time

import chrome
import notify
from cdp import CDPError, Page, open_page
from common import DATA, log
from envfile import get

STATE = DATA / ".krx_login_state.json"
MAX_FAIL_STREAK = 2          # 이만큼 연속 실패하면 잠금 (KRX 계정잠금 5회보다 넉넉히 아래)

_VIS = """
const vis = el => {
  if (!el) return false;
  const w = el.ownerDocument.defaultView || window;
  const r = el.getBoundingClientRect(), s = w.getComputedStyle(el);
  return r.width > 1 && r.height > 1 && s.visibility !== 'hidden' && s.display !== 'none';
};
// 2026-08 KRX가 로그인 폼을 같은 도메인 iframe(login.jsp) 안으로 옮겼다
const docs = (() => {
  const out = [document];
  for (const f of document.querySelectorAll('iframe')) {
    try { if (f.contentDocument) out.push(f.contentDocument); } catch (e) {}
  }
  return out;
})();
const pwField = () => {
  for (const d of docs) {
    const hit = [...d.querySelectorAll('input[type=password]')].filter(vis)[0];
    if (hit) return hit;
  }
  return null;
};
"""

_JS_FIND = _VIS + """
(() => {
  const pw = pwField();
  if (!pw) return {ok:false, reason:'비밀번호 입력칸을 찾지 못했습니다',
                   title: document.title, url: location.href};
  const scope = pw.form || pw.ownerDocument;
  const skip = ['hidden','checkbox','radio','submit','button','image','file'];
  const texts = [...scope.querySelectorAll('input')].filter(
      i => i !== pw && vis(i) && !skip.includes(i.type));
  let idf = null;
  for (const t of texts) {
    if (t.compareDocumentPosition(pw) & Node.DOCUMENT_POSITION_FOLLOWING) idf = t;
  }
  if (!idf) idf = texts[0] || null;
  const desc = el => el ? {name: el.name || null, id: el.id || null,
                           type: el.type, ph: el.placeholder || null} : null;
  return {ok: !!idf, reason: idf ? null : '아이디 입력칸을 찾지 못했습니다',
          id: desc(idf), pw: desc(pw), inForm: !!pw.form, url: location.href};
})()
"""

_JS_FILL = _VIS + """
((uid, upw) => {
  const pw = pwField();
  if (!pw) return {ok:false, reason:'비밀번호 입력칸 사라짐'};
  const scope = pw.form || pw.ownerDocument;
  const skip = ['hidden','checkbox','radio','submit','button','image','file'];
  const texts = [...scope.querySelectorAll('input')].filter(
      i => i !== pw && vis(i) && !skip.includes(i.type));
  let idf = null;
  for (const t of texts) {
    if (t.compareDocumentPosition(pw) & Node.DOCUMENT_POSITION_FOLLOWING) idf = t;
  }
  if (!idf) idf = texts[0];
  if (!idf) return {ok:false, reason:'아이디 입력칸 없음'};

  const set = (el, v) => {
    el.focus();
    const d = Object.getOwnPropertyDescriptor(Object.getPrototypeOf(el), 'value');
    if (d && d.set) d.set.call(el, v); else el.value = v;
    for (const t of ['input','change','keyup','blur'])
      el.dispatchEvent(new Event(t, {bubbles:true}));
  };
  set(idf, uid);
  set(pw, upw);
  return {ok: idf.value === uid && pw.value.length === upw.length,
          idName: idf.name || idf.id || '(무명)'};
})(%s, %s)
"""

_JS_SUBMIT = _VIS + """
(() => {
  const pw = pwField();
  if (!pw) return {ok:false, reason:'비밀번호 입력칸 사라짐'};
  const form = pw.form;
  const looksLogin = el => {
    const t = ((el.innerText || '') + ' ' + (el.value || '') + ' ' +
               (el.getAttribute('title') || '') + ' ' +
               (el.getAttribute('alt') || '')).trim();
    return /로그인|LOG\\s?IN/i.test(t) && t.length < 30;
  };
  const sel = 'a,button,input[type=submit],input[type=button],input[type=image]';

  if (form) {
    const inForm = [...form.querySelectorAll(sel)].filter(vis);
    const btn = inForm.find(looksLogin) ||
                inForm.find(el => el.type === 'submit' || el.type === 'image');
    if (btn) { btn.click(); return {ok:true, how:'폼 내 버튼', label:(btn.innerText||btn.value||btn.type).trim().slice(0,20)}; }
  }
  // 폼 밖에 버튼이 있는 화면 대비 — 비밀번호 칸과 가까운 것부터
  const pr = pw.getBoundingClientRect();
  const near = [...pw.ownerDocument.querySelectorAll(sel)].filter(el => vis(el) && looksLogin(el))
    .map(el => { const r = el.getBoundingClientRect();
                 return {el, d: Math.hypot(r.x - pr.x, r.y - pr.y)}; })
    .filter(o => o.d < 600).sort((a,b) => a.d - b.d);
  if (near.length) {
    near[0].el.click();
    return {ok:true, how:'인접 버튼', label:(near[0].el.innerText||near[0].el.value||'').trim().slice(0,20)};
  }
  // 마지막 수단 — 비밀번호 칸에서 엔터
  pw.focus();
  for (const type of ['keydown','keypress','keyup'])
    pw.dispatchEvent(new KeyboardEvent(type, {bubbles:true, key:'Enter',
                                              code:'Enter', keyCode:13, which:13}));
  if (form && form.requestSubmit) { try { form.requestSubmit(); } catch (e) {} }
  return {ok:true, how:'엔터키'};
})()
"""


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


def record_fail(s: dict, reason: str) -> bool:
    """실패를 기록하고, 잠금 모드로 들어갔으면 True."""
    s["fail_streak"] = int(s.get("fail_streak", 0)) + 1
    s["last_fail"] = _now()
    s["last_reason"] = reason
    newly_locked = False
    if s["fail_streak"] >= MAX_FAIL_STREAK and not s.get("locked"):
        s["locked"] = True
        newly_locked = True
    save_state(s)

    log(f"로그인 실패({s['fail_streak']}/{MAX_FAIL_STREAK}): {reason}")
    if newly_locked:
        notify.send(
            f"⛔ KRX 자동 로그인 {s['fail_streak']}회 연속 실패 — 자동 시도를 멈췄습니다.\n"
            f"사유: {reason}\n\n"
            f"계정 잠금(5회)을 피하려고 더는 시도하지 않습니다. "
            f"비밀번호·계정 상태를 확인한 뒤 맥미니에서 아래를 실행해 주세요.\n"
            f"  cd ~/short-dashboard && .venv/bin/python scripts/krx_login.py --reset\n"
            f"공매도 숫자는 그때까지 직전 값으로 유지됩니다.",
            dedupe="krx-login-failed", cooldown_h=12)
    return newly_locked


# ---------------------------------------------------------------- 로그인
def session_alive() -> bool:
    """현재 크롬 쿠키로 로그인 상태인지."""
    import krx_session
    try:
        s = krx_session.build_session(verify=False)
        ok, _ = krx_session.check_session(s)
        return ok
    except Exception:
        return False


def do_login(page: Page, uid: str, pw: str, *, dry_run: bool = False) -> tuple[bool, str]:
    """로그인 폼을 찾아 채우고 제출한다. (성공여부, 사유)"""
    page.navigate(chrome.LOGIN_URL, settle=3.5)

    found = page.evaluate(_JS_FIND)
    if not found or not found.get("ok"):
        return False, (found or {}).get("reason", "로그인 폼 탐색 실패")
    log(f"로그인 폼 확인 — 아이디칸 {found['id']} / 비밀번호칸 {found['pw']}")

    filled = page.evaluate(_JS_FILL % (json.dumps(uid), json.dumps(pw)))
    if not filled or not filled.get("ok"):
        return False, (filled or {}).get("reason", "폼 입력 실패")
    log(f"계정 입력 완료 (아이디칸 {filled.get('idName')})")

    if dry_run:
        return False, "--dry-run: 제출하지 않음 (크롬 창에서 값이 들어갔는지 확인하세요)"

    sub = page.evaluate(_JS_SUBMIT)
    log(f"제출: {sub.get('how')} {sub.get('label') or ''}".strip())
    page.wait_ready(timeout=25, settle=3.0)
    time.sleep(2.0)                      # 로그인 후 리다이렉트 여유

    for _ in range(3):                   # 쿠키가 반영될 때까지 몇 초 더
        if session_alive():
            return True, "OK"
        time.sleep(2.5)
    return False, f"제출했으나 로그인 상태가 아님 (현재 {page.url()[:80]})"


def ensure_login(*, force: bool = False, dry_run: bool = False) -> bool:
    """필요하면 로그인한다. 이미 살아 있으면 아무것도 하지 않는다."""
    st = load_state()

    if not force and session_alive():
        log("KRX 세션 이미 유효 — 로그인 생략")
        if st.get("fail_streak"):
            record_ok(st)
        return True

    if st.get("locked"):
        log(f"자동 로그인 잠금 상태 (연속 {st.get('fail_streak')}회 실패, "
            f"마지막 사유: {st.get('last_reason')}) — 시도하지 않습니다.")
        log("  해제: python scripts/krx_login.py --reset")
        notify.send(
            "KRX 자동 로그인이 잠금 상태라 이번 갱신에서도 공매도를 건너뜁니다.\n"
            "확인 후 `krx_login.py --reset` 을 실행해 주세요.",
            dedupe="krx-login-locked", cooldown_h=24)
        return False

    uid, pw = get("KRX_ID"), get("KRX_PW")
    if not (uid and pw):
        log("KRX_ID / KRX_PW 가 .env 에 없습니다 — 자동 로그인 불가")
        notify.send(
            "KRX_ID / KRX_PW 가 .env 에 없어 자동 로그인을 못 합니다.\n"
            "맥미니의 short-dashboard/.env 에 계정을 넣어주세요.",
            dedupe="krx-cred-missing", cooldown_h=24)
        return False

    if not chrome.launch():
        log("크롬을 띄우지 못해 로그인할 수 없습니다.")
        notify.send(
            "맥미니에서 크롬(원격 디버깅 9222)을 띄우지 못했습니다.\n"
            "화면 잠금/자동 로그인 설정을 확인해 주세요.",
            dedupe="chrome-launch-failed", cooldown_h=12)
        return False

    log(f"KRX 자동 로그인 시도 (계정 {uid[:2]}***, 이번 호출 1회만)")
    try:
        with open_page("krx.co.kr") as page:
            ok, reason = do_login(page, uid, pw, dry_run=dry_run)
    except CDPError as e:
        ok, reason = False, f"CDP 오류: {e}"

    if ok:
        log("✅ KRX 자동 로그인 성공")
        record_ok(st)
        return True

    if dry_run:
        log(reason)
        return False

    record_fail(st, reason)
    return False


# ---------------------------------------------------------------- CLI
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="이미 로그인돼 있어도 다시")
    ap.add_argument("--dry-run", action="store_true", help="입력만 하고 제출 안 함")
    ap.add_argument("--status", action="store_true", help="상태만 출력")
    ap.add_argument("--reset", action="store_true", help="실패 누적·잠금 해제")
    a = ap.parse_args()

    if a.reset:
        s = load_state()
        s.update(fail_streak=0, locked=False, last_reason=None)
        save_state(s)
        notify.clear("krx-login-failed")
        notify.clear("krx-login-locked")
        print("✅ 잠금 해제. 다음 실행에서 자동 로그인을 다시 시도합니다.")
        return 0

    if a.status:
        s = load_state()
        alive = session_alive()
        print(f"세션      : {'유효' if alive else '없음/만료'}")
        print(f"연속 실패 : {s.get('fail_streak', 0)} / {MAX_FAIL_STREAK}")
        print(f"잠금      : {'예 — --reset 필요' if s.get('locked') else '아니오'}")
        print(f"마지막 성공: {s.get('last_ok') or '-'}")
        print(f"마지막 실패: {s.get('last_fail') or '-'} {s.get('last_reason') or ''}")
        return 0 if alive else 1

    ok = ensure_login(force=a.force, dry_run=a.dry_run)
    print("\n✅ KRX 로그인 세션 사용 가능" if ok else "\n❌ KRX 로그인 실패 — 위 로그를 확인하세요")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
