# -*- coding: utf-8 -*-
"""열려있는 모든 탭의 XHR/fetch 요청을 캡처한다 (KRX·KOFIA 등 도메인 무관).

사용: py scripts/cdp_listen_all.py [초]
크롬에서 원하는 화면의 '조회'를 누르면 그 요청(URL + POST 본문)이 찍힌다.
"""
from __future__ import annotations

import json
import sys
import threading
import time
import urllib.parse
import urllib.request

import websocket

CDP = "http://127.0.0.1:9222"
SKIP = (".js", ".css", ".png", ".jpg", ".gif", ".svg", ".woff", ".ico", ".map")
NOISE = ("google", "doubleclick", "analytics", "gtm.", "facebook", "/MAIN/MDCMAIN")

_lock = threading.Lock()
_hits: list[dict] = []


def targets():
    with urllib.request.urlopen(f"{CDP}/json", timeout=5) as r:
        return [t for t in json.load(r) if t.get("type") == "page"]


def watch(t: dict, deadline: float) -> None:
    try:
        ws = websocket.create_connection(t["webSocketDebuggerUrl"], timeout=30,
                                         suppress_origin=True)
    except Exception as e:
        print(f"  [!] 탭 연결 실패: {e}")
        return
    ws.send(json.dumps({"id": 1, "method": "Network.enable"}))
    ws.settimeout(2.0)
    host = urllib.parse.urlparse(t.get("url", "")).netloc
    seen = set()
    while time.time() < deadline:
        try:
            msg = json.loads(ws.recv())
        except websocket.WebSocketTimeoutException:
            continue
        except Exception:
            break
        if msg.get("method") != "Network.requestWillBeSent":
            continue
        p = msg["params"]
        req = p["request"]
        url = req.get("url", "")
        rtype = p.get("type", "")
        if rtype not in ("XHR", "Fetch"):
            continue
        if url.lower().split("?")[0].endswith(SKIP):
            continue
        if any(n in url for n in NOISE):
            continue
        post = req.get("postData") or ""
        key = (url, post)
        if key in seen:
            continue
        seen.add(key)
        rec = {"tab": host, "method": req.get("method"), "url": url, "postData": post}
        with _lock:
            _hits.append(rec)
            print(f"\n  [{host}] {req.get('method')} {url[:120]}")
            if post:
                try:
                    kv = dict(urllib.parse.parse_qsl(post))
                    if kv:
                        for k, v in kv.items():
                            print(f"        {k} = {v}")
                    else:
                        print(f"        body: {post[:400]}")
                except Exception:
                    print(f"        body: {post[:400]}")
            print(flush=True)
    ws.close()


def main():
    wait = float(sys.argv[1]) if len(sys.argv) > 1 else 240.0
    ts = targets()
    if not ts:
        print("[!] 탭 없음")
        return
    print(f"[listen-all] {len(ts)}개 탭 감시, {wait:.0f}초")
    for t in ts:
        print(f"   - {urllib.parse.urlparse(t.get('url','')).netloc}  {t.get('title','')[:40]}")
    print("\n   화면에서 '조회'를 눌러주세요.\n", flush=True)

    deadline = time.time() + wait
    threads = [threading.Thread(target=watch, args=(t, deadline), daemon=True)
               for t in ts]
    for th in threads:
        th.start()
    for th in threads:
        th.join()

    print("\n===== 캡처 결과 =====")
    print(json.dumps(_hits, ensure_ascii=False, indent=1)[:6000])


if __name__ == "__main__":
    main()
