# -*- coding: utf-8 -*-
"""아주 얇은 CDP(Chrome DevTools Protocol) 클라이언트.

krx_session.py 는 쿠키만 읽으면 되지만, 자동 로그인은 페이지를 이동시키고
DOM 을 조작해야 해서 Runtime.evaluate / Page.navigate 가 필요하다.
셀레니움을 끌어오지 않고 websocket-client 하나로 처리한다.
"""
from __future__ import annotations

import json
import time

import websocket  # websocket-client

from chrome import CDP_HOST, targets


class CDPError(RuntimeError):
    pass


class Page:
    """열려 있는 탭 하나에 붙어 명령을 보낸다."""

    def __init__(self, ws_url: str, timeout: float = 30.0):
        self._ws = websocket.create_connection(
            ws_url, timeout=timeout, origin="", suppress_origin=True)
        self._id = 0

    # --- 저수준 ---------------------------------------------------------
    def call(self, method: str, params: dict | None = None,
             timeout: float = 30.0) -> dict:
        self._id += 1
        mid = self._id
        self._ws.send(json.dumps({"id": mid, "method": method,
                                  "params": params or {}}))
        deadline = time.time() + timeout
        while time.time() < deadline:
            self._ws.settimeout(max(0.5, deadline - time.time()))
            try:
                msg = json.loads(self._ws.recv())
            except websocket.WebSocketTimeoutException:
                continue
            if msg.get("id") != mid:
                continue                        # 이벤트/다른 응답은 흘려보낸다
            if "error" in msg:
                raise CDPError(f"{method}: {msg['error'].get('message')}")
            return msg.get("result", {})
        raise CDPError(f"{method}: 응답 시간 초과")

    def close(self) -> None:
        try:
            self._ws.close()
        except Exception:
            pass

    def __enter__(self) -> "Page":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # --- 고수준 ---------------------------------------------------------
    def evaluate(self, expr: str, *, await_promise: bool = False,
                 timeout: float = 30.0):
        """JS 를 평가해 JSON 직렬화 가능한 값을 돌려받는다."""
        r = self.call("Runtime.evaluate", {
            "expression": expr,
            "returnByValue": True,
            "awaitPromise": await_promise,
            "userGesture": True,
        }, timeout=timeout)
        if r.get("exceptionDetails"):
            detail = r["exceptionDetails"]
            msg = (detail.get("exception", {}).get("description")
                   or detail.get("text") or "JS 예외")
            raise CDPError(str(msg).splitlines()[0][:200])
        return r.get("result", {}).get("value")

    def navigate(self, url: str, *, settle: float = 3.0) -> None:
        self.call("Page.enable")
        self.call("Page.navigate", {"url": url})
        self.wait_ready(settle=settle)

    def wait_ready(self, *, timeout: float = 25.0, settle: float = 2.0) -> bool:
        """document.readyState 가 complete 가 될 때까지 기다린다."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                if self.evaluate("document.readyState", timeout=8) == "complete":
                    time.sleep(settle)          # SPA 스크립트가 DOM 을 마저 그릴 여유
                    return True
            except CDPError:
                pass                            # 내비게이션 중에는 잠깐 끊길 수 있다
            time.sleep(0.5)
        return False

    def url(self) -> str:
        try:
            return self.evaluate("location.href") or ""
        except CDPError:
            return ""


def open_page(match: str | None = None, *, timeout: float = 30.0) -> Page:
    """탭을 고른다. match 가 URL 에 들어간 탭을 우선, 없으면 첫 페이지 탭."""
    try:
        tabs = [t for t in targets() if t.get("type") == "page"
                and t.get("webSocketDebuggerUrl")]
    except Exception as e:
        raise CDPError(f"9222 에 연결할 수 없습니다: {e}") from e
    if not tabs:
        raise CDPError("크롬에 열린 페이지 탭이 없습니다.")
    if match:
        hit = [t for t in tabs if match in (t.get("url") or "")]
        if hit:
            tabs = hit
    return Page(tabs[0]["webSocketDebuggerUrl"], timeout=timeout)


def new_tab(url: str = "about:blank") -> dict:
    """빈 탭 하나를 연다 (기존 탭을 건드리지 않을 때)."""
    import urllib.parse
    import urllib.request
    q = urllib.parse.quote(url, safe=":/?=&")
    with urllib.request.urlopen(f"{CDP_HOST}/json/new?{q}", timeout=10) as r:
        return json.load(r)
