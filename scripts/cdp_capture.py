# -*- coding: utf-8 -*-
"""CDP로 KRX 화면을 열고 브라우저가 실제로 보내는 getJsonData 요청을 캡처한다.

사용: py scripts/cdp_capture.py MDC02030301 [초]
"""
from __future__ import annotations

import json
import sys
import time
import urllib.parse
import urllib.request

import websocket

CDP = "http://127.0.0.1:9222"
LOADER = "https://data.krx.co.kr/contents/MDC/MDI/mdiLoader/index.cmd?menuId="

CLICK_JS = r"""
(()=>{
  const sels=['.CI-MDI-UNIT-BTN-SEARCH','#jsSearchButton','a[href*="search"]',
              '.btn-search','button','a','input'];
  for(const sel of sels){
    for(const e of document.querySelectorAll(sel)){
      const t=(e.textContent||e.value||'').trim();
      if(t==='조회' || t==='검색'){ e.click(); return 'clicked:'+sel+':'+t; }
    }
  }
  const all=[...document.querySelectorAll('a,button,input')]
    .map(e=>(e.textContent||e.value||'').trim()).filter(Boolean).slice(0,40);
  return 'no-button; visible='+JSON.stringify(all);
})()
"""


def page_target():
    with urllib.request.urlopen(f"{CDP}/json", timeout=5) as r:
        ts = json.load(r)
    pages = [t for t in ts if t.get("type") == "page"]
    krx = [p for p in pages if "krx.co.kr" in (p.get("url") or "")]
    return (krx or pages)[0]


def main():
    menu = sys.argv[1] if len(sys.argv) > 1 else "MDC02030301"
    wait = float(sys.argv[2]) if len(sys.argv) > 2 else 14.0

    t = page_target()
    ws = websocket.create_connection(t["webSocketDebuggerUrl"], timeout=40,
                                     suppress_origin=True)
    mid = [0]

    def send(method, params=None):
        mid[0] += 1
        ws.send(json.dumps({"id": mid[0], "method": method, "params": params or {}}))
        return mid[0]

    send("Network.enable")
    send("Page.enable")
    send("Runtime.enable")
    time.sleep(0.4)
    send("Page.navigate", {"url": LOADER + menu})

    print(f"[capture] menuId={menu}, {wait:.0f}s ...")
    captured, seen = [], set()
    clicked = 0
    click_ids = set()
    end = time.time() + wait
    ws.settimeout(2.0)
    while time.time() < end:
        try:
            msg = json.loads(ws.recv())
        except websocket.WebSocketTimeoutException:
            if clicked < 3:
                clicked += 1
                click_ids.add(send("Runtime.evaluate",
                                   {"expression": CLICK_JS, "returnByValue": True}))
                print(f"  -> click attempt #{clicked}")
            continue
        if msg.get("id") in click_ids:
            val = (msg.get("result", {}).get("result", {}) or {}).get("value")
            print(f"     click result: {str(val)[:300]}")
            continue
        if msg.get("method") != "Network.requestWillBeSent":
            continue
        req = msg["params"]["request"]
        url = req.get("url", "")
        if "getJsonData.cmd" not in url and "bldAttendant" not in url:
            continue
        post = req.get("postData") or ""
        if post in seen:
            continue
        seen.add(post)
        params = dict(urllib.parse.parse_qsl(post))
        if not params.get("bld"):
            continue
        captured.append(params)
        print(f"\n  [OK] bld = {params.get('bld')}")
        for k, v in sorted(params.items()):
            if k != "bld" and v:
                print(f"       {k} = {v}")
    ws.close()

    if not captured:
        print("\n  [!] no request captured. Click the search button in Chrome manually.")
    print("\n" + json.dumps(captured, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
