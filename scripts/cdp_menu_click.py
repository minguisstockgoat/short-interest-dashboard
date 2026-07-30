# -*- coding: utf-8 -*-
"""SPA 메뉴 링크(data-menu-id)를 직접 클릭해 화면을 띄우고 요청을 캡처한다.

사용: py scripts/cdp_menu_click.py MDC02030501 [초]
"""
from __future__ import annotations

import json
import sys
import time
import urllib.parse
import urllib.request

import websocket

CDP = "http://127.0.0.1:9222"
HOME = "https://data.krx.co.kr/contents/MDC/MAIN/main/index.cmd"

MENU_JS = """
(()=>{
  const el=document.querySelector('[data-menu-id="%s"]');
  if(!el) return 'menu-not-found';
  el.click();
  return 'menu-clicked:'+el.textContent.trim();
})()
"""
SEARCH_JS = r"""
(()=>{
  const els=[...document.querySelectorAll('a,button,input')];
  const b=els.find(e=>{const t=(e.textContent||e.value||'').trim();
                       return t==='조회'||t==='검색';});
  if(b){ b.click(); return 'search-clicked'; }
  return 'no-search-button';
})()
"""


def page_target():
    with urllib.request.urlopen(f"{CDP}/json", timeout=5) as r:
        ts = json.load(r)
    pages = [t for t in ts if t.get("type") == "page"]
    krx = [p for p in pages if "krx.co.kr" in (p.get("url") or "")]
    return (krx or pages)[0]


def main():
    menu = sys.argv[1] if len(sys.argv) > 1 else "MDC02030501"
    wait = float(sys.argv[2]) if len(sys.argv) > 2 else 30.0

    t = page_target()
    ws = websocket.create_connection(t["webSocketDebuggerUrl"], timeout=60,
                                     suppress_origin=True)
    mid = [0]
    evals = {}

    def send(method, params=None, tag=""):
        mid[0] += 1
        ws.send(json.dumps({"id": mid[0], "method": method, "params": params or {}}))
        if tag:
            evals[mid[0]] = tag
        return mid[0]

    send("Network.enable")
    send("Page.enable")
    send("Runtime.enable")
    time.sleep(0.3)
    send("Page.navigate", {"url": HOME})
    print(f"[capture] menu={menu}, {wait:.0f}s ...")

    captured, seen = [], set()
    stage, next_at = 0, time.time() + 5
    end = time.time() + wait
    ws.settimeout(1.5)
    while time.time() < end:
        if time.time() > next_at:
            if stage == 0:
                send("Runtime.evaluate",
                     {"expression": MENU_JS % menu, "returnByValue": True}, "menu")
                stage, next_at = 1, time.time() + 6
            elif stage <= 3:
                send("Runtime.evaluate",
                     {"expression": SEARCH_JS, "returnByValue": True}, "search")
                stage, next_at = stage + 1, time.time() + 6
            else:
                next_at = time.time() + 999
        try:
            msg = json.loads(ws.recv())
        except websocket.WebSocketTimeoutException:
            continue
        if msg.get("id") in evals:
            v = (msg.get("result", {}).get("result", {}) or {}).get("value")
            print(f"     [{evals[msg['id']]}] {str(v)[:160]}")
            continue
        if msg.get("method") != "Network.requestWillBeSent":
            continue
        req = msg["params"]["request"]
        if "getJsonData.cmd" not in req.get("url", ""):
            continue
        post = req.get("postData") or ""
        if post in seen:
            continue
        seen.add(post)
        p = dict(urllib.parse.parse_qsl(post))
        if not p.get("bld"):
            continue
        captured.append(p)
        print(f"\n  [OK] bld = {p['bld']}")
        for k, v in sorted(p.items()):
            if k != "bld" and v:
                print(f"       {k} = {v}")
    ws.close()
    print("\n" + json.dumps(captured, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
