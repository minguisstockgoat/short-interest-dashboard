# -*- coding: utf-8 -*-
"""launch_chrome.ps1 로 띄운 크롬(원격 디버깅 9222)에서 KRX 로그인 세션을 빌려온다.

CDP(Chrome DevTools Protocol)의 Network.getCookies 로 HttpOnly 쿠키(JSESSIONID)까지
읽어 requests.Session 에 실어준다. 이후 수집은 순수 파이썬으로 빠르게 돈다.
비밀번호는 다루지 않는다 — 로그인은 사용자가 크롬 창에서 직접 한다.
"""
from __future__ import annotations

import json
import sys
import urllib.request

import requests
import websocket  # websocket-client

from common import ROOT, log

CDP_HOST = "http://127.0.0.1:9222"
KRX_ORIGIN = "https://data.krx.co.kr"
JSON_URL = f"{KRX_ORIGIN}/comm/bldAttendant/getJsonData.cmd"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")


class ChromeNotRunning(RuntimeError):
    pass


class NotLoggedIn(RuntimeError):
    pass


def _targets() -> list[dict]:
    try:
        with urllib.request.urlopen(f"{CDP_HOST}/json", timeout=5) as r:
            return json.load(r)
    except Exception as e:
        if sys.platform == "darwin":
            how = f"     bash {ROOT / 'mac' / 'launch_chrome.sh'}"
        else:
            how = (f"     powershell -ExecutionPolicy Bypass -File "
                   f"{ROOT / 'launch_chrome.ps1'}")
        raise ChromeNotRunning(
            "127.0.0.1:9222 에 붙을 수 없습니다.\n"
            "  → 아래를 실행하고 KRX 로그인을 먼저 해주세요.\n" + how
        ) from e


def _pick_page() -> dict:
    pages = [t for t in _targets() if t.get("type") == "page"]
    if not pages:
        raise ChromeNotRunning("크롬에 열린 페이지 탭이 없습니다.")
    krx = [p for p in pages if "krx.co.kr" in (p.get("url") or "")]
    return (krx or pages)[0]


def get_cookies(domain_filter: str = "krx.co.kr") -> list[dict]:
    """CDP로 브라우저 쿠키 전체를 읽어 KRX 도메인 것만 반환 (HttpOnly 포함)."""
    page = _pick_page()
    ws = websocket.create_connection(page["webSocketDebuggerUrl"],
                                     timeout=15, origin="", suppress_origin=True)
    try:
        ws.send(json.dumps({"id": 1, "method": "Network.enable"}))
        ws.recv()
        ws.send(json.dumps({"id": 2, "method": "Network.getAllCookies"}))
        while True:
            msg = json.loads(ws.recv())
            if msg.get("id") == 2:
                cookies = msg["result"]["cookies"]
                break
    finally:
        ws.close()
    return [c for c in cookies if domain_filter in c.get("domain", "")]


def build_session(verify: bool = True) -> requests.Session:
    """크롬 쿠키를 실은 requests.Session 을 만든다."""
    cookies = get_cookies()
    if not cookies:
        raise NotLoggedIn("KRX 쿠키가 없습니다. 크롬에서 data.krx.co.kr 로그인을 먼저 해주세요.")

    s = requests.Session()
    s.headers.update({
        "User-Agent": UA,
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Accept-Language": "ko-KR,ko;q=0.9",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "Origin": KRX_ORIGIN,
        "Referer": f"{KRX_ORIGIN}/contents/MDC/MDI/mdiLoader/index.cmd",
        "X-Requested-With": "XMLHttpRequest",
    })
    for c in cookies:
        s.cookies.set(c["name"], c["value"],
                      domain=c["domain"].lstrip("."), path=c.get("path", "/"))
    names = sorted({c["name"] for c in cookies})
    log(f"크롬 세션 쿠키 {len(cookies)}개 확보: {', '.join(names[:8])}")

    if verify:
        ok, note = check_session(s)
        if not ok:
            raise NotLoggedIn(f"세션이 로그인 상태가 아닙니다 ({note}). "
                              "크롬 창에서 KRX 로그인 후 다시 시도하세요.")
        log(f"로그인 세션 확인 OK ({note})")
    return s


def check_session(s: requests.Session) -> tuple[bool, str]:
    """가벼운 bld 호출로 로그인 여부를 확인한다."""
    r = s.post(JSON_URL, data={
        "bld": "dbms/MDC/STAT/standard/MDCSTAT01501", "locale": "ko_KR",
        "mktId": "ALL", "trdDd": "20260729", "share": "1", "money": "1",
        "csvxls_isNo": "false"}, timeout=30)
    body = r.text.strip()
    if body.startswith("{"):
        js = r.json()
        key = next((k for k in js if isinstance(js[k], list)), None)
        n = len(js.get(key) or []) if key else 0
        return True, f"전종목시세 {n}건 응답"
    return False, f"HTTP {r.status_code} / {body[:40]}"


if __name__ == "__main__":
    try:
        build_session()
        print("\n✅ KRX 로그인 세션 사용 가능. 이제 수집을 시작할 수 있습니다.")
    except (ChromeNotRunning, NotLoggedIn) as e:
        print(f"\n❌ {e}")
