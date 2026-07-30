# -*- coding: utf-8 -*-
"""열려있는 크롬(CDP 9222)으로 대시보드를 열어 스크린샷을 저장한다."""
from __future__ import annotations

import base64
import json
import sys
import time
import urllib.request

import websocket

CDP = "http://127.0.0.1:9222"
URL = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8765/index.html"
OUT = sys.argv[2] if len(sys.argv) > 2 else "dashboard.png"
WIDTH, HEIGHT = 1680, 1050


def main():
    with urllib.request.urlopen(f"{CDP}/json", timeout=5) as r:
        ts = json.load(r)
    pages = [t for t in ts if t.get("type") == "page"]
    if not pages:
        print("[!] 페이지 탭 없음")
        return
    ws = websocket.create_connection(pages[0]["webSocketDebuggerUrl"],
                                     timeout=60, suppress_origin=True)
    mid = [0]

    def call(method, params=None, wait=True):
        mid[0] += 1
        i = mid[0]
        ws.send(json.dumps({"id": i, "method": method, "params": params or {}}))
        if not wait:
            return None
        while True:
            m = json.loads(ws.recv())
            if m.get("id") == i:
                return m.get("result", {})

    call("Page.enable")
    call("Emulation.setDeviceMetricsOverride",
         {"width": WIDTH, "height": HEIGHT, "deviceScaleFactor": 1, "mobile": False})
    call("Page.navigate", {"url": URL})
    time.sleep(6)
    res = call("Page.captureScreenshot", {"format": "png"})
    ws.close()
    data = res.get("data")
    if not data:
        print("[!] 캡처 실패")
        return
    with open(OUT, "wb") as f:
        f.write(base64.b64decode(data))
    print(f"저장: {OUT}")


if __name__ == "__main__":
    main()
