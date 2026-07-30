# -*- coding: utf-8 -*-
"""수동 조작을 기다리며 getJsonData 요청을 수동적으로 캡처한다 (네비게이션 없음).

사용: py scripts/cdp_listen.py [초]
크롬 창에서 원하는 화면을 열고 '조회'를 누르면 그 요청이 여기에 찍힌다.
"""
from __future__ import annotations

import json
import sys
import time
import urllib.parse
import urllib.request

import websocket

CDP = "http://127.0.0.1:9222"


def page_targets():
    with urllib.request.urlopen(f"{CDP}/json", timeout=5) as r:
        ts = json.load(r)
    return [t for t in ts if t.get("type") == "page" and "krx.co.kr" in (t.get("url") or "")]


def main():
    wait = float(sys.argv[1]) if len(sys.argv) > 1 else 120.0
    targets = page_targets()
    if not targets:
        print("[!] KRX 탭을 찾지 못했습니다.")
        return
    t = targets[0]
    print(f"[listen] {t.get('title', '')[:40]} — {wait:.0f}초 대기")
    print("        크롬에서 [통계 > 공매도 통계 > 대차 정보 > 대차거래 추이] → [조회] 를 눌러주세요.\n")

    ws = websocket.create_connection(t["webSocketDebuggerUrl"], timeout=60,
                                     suppress_origin=True)
    ws.send(json.dumps({"id": 1, "method": "Network.enable"}))

    captured, seen = [], set()
    end = time.time() + wait
    ws.settimeout(2.0)
    last_beat = 0
    while time.time() < end:
        remain = int(end - time.time())
        if remain // 15 != last_beat:
            last_beat = remain // 15
            print(f"  … 대기중 ({remain}초 남음)", flush=True)
        try:
            msg = json.loads(ws.recv())
        except websocket.WebSocketTimeoutException:
            continue
        except Exception:
            break
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
        bld = p.get("bld", "")
        if not bld or "/MAIN/" in bld:
            continue
        captured.append(p)
        print(f"\n  [OK] bld = {bld}")
        for k, v in sorted(p.items()):
            if k != "bld" and v:
                print(f"       {k} = {v}")
        print(flush=True)
    ws.close()
    print("\n===== 캡처 결과 =====")
    print(json.dumps(captured, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
