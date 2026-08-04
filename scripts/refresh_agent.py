# -*- coding: utf-8 -*-
"""대시보드 '수동 갱신' 버튼을 받는 로컬 에이전트.

  python scripts/refresh_agent.py                 # 127.0.0.1:8766
  python scripts/refresh_agent.py --host 0.0.0.0  # 같은 네트워크에 개방
  python scripts/refresh_agent.py --port 9000

GitHub Pages 는 정적 사이트라 페이지가 직접 파이프라인을 돌릴 수 없다. 그래서
갱신을 실제로 수행하는 머신(맥미니)에서 이 작은 서버를 띄워두고, 대시보드의
버튼이 여기로 요청을 보낸다.

  GET  /status   현재 상태(실행 중 여부·기준일·세션·로그인 잠금)
  POST /refresh  파이프라인 시작 (이미 돌고 있으면 무시)
  GET  /log      진행 중인 로그 꼬리

브라우저 제약 — https 페이지에서 http 로 요청할 수 있는 예외는 localhost 뿐이다.
즉 이 에이전트가 도는 그 컴퓨터에서 대시보드를 열었을 때 버튼이 살아난다.
다른 기기에서도 쓰려면 에이전트를 https 로 노출(예: Cloudflare Tunnel)한 뒤
대시보드 버튼을 길게 눌러 그 주소를 등록하면 된다.

.env 의 AGENT_TOKEN 을 설정하면 요청에 X-Agent-Token 헤더를 요구한다.
127.0.0.1 에만 묶어 쓸 거라면 없어도 무방하다.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import threading
import datetime as dt
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from common import DATA, ROOT, log
from envfile import get

SCRIPTS = ROOT / "scripts"
LOGS = ROOT / "logs"
DOCS = ROOT / "docs"
STATUS = DATA / ".pipeline_status.json"
KEEPALIVE = DATA / ".keepalive.json"

ALLOWED_ORIGINS = {
    "https://minguisstockgoat.github.io",
    "http://127.0.0.1:8765", "http://localhost:8765",
}

_proc: subprocess.Popen | None = None
_log_path: Path | None = None
_lock = threading.Lock()


# ------------------------------------------------------------------ 상태
def _read(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def running() -> bool:
    global _proc
    with _lock:
        if _proc is None:
            return False
        if _proc.poll() is None:
            return True
        _proc = None
        return False


def snapshot() -> dict:
    import krx_login

    st = krx_login.load_state()
    meta = {}
    try:
        meta = json.loads((DOCS / "dashboard_data.json")
                          .read_text(encoding="utf-8"))["meta"]
    except (OSError, ValueError, KeyError):
        pass

    return {
        "running": running(),
        "pipeline": _read(STATUS),
        "keepalive": _read(KEEPALIVE),
        "login": {
            "locked": bool(st.get("locked")),
            "failStreak": st.get("fail_streak", 0),
            "lastOk": st.get("last_ok"),
            "lastFail": st.get("last_fail"),
            "lastReason": st.get("last_reason"),
        },
        "data": {k: meta.get(k) for k in
                 ("asof", "knownDate", "shortStaleDays", "generatedAt")},
        "serverTime": dt.datetime.now().isoformat(timespec="seconds"),
    }


def start_refresh(days: int = 7) -> dict:
    """파이프라인을 백그라운드로 시작한다."""
    global _proc, _log_path
    if running():
        return {"ok": False, "reason": "이미 갱신이 진행 중입니다."}

    LOGS.mkdir(exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    path = LOGS / f"manual_{stamp}.log"
    fh = path.open("w", encoding="utf-8")
    cmd = [sys.executable, str(SCRIPTS / "pipeline.py"),
           "--days", str(days), "--deploy", "--source", "manual"]
    log(f"수동 갱신 시작 → {path.name}")
    with _lock:
        _proc = subprocess.Popen(cmd, cwd=str(ROOT), stdout=fh,
                                 stderr=subprocess.STDOUT, text=True)
        _log_path = path
    return {"ok": True, "log": path.name}


def tail(n: int = 40) -> list[str]:
    path = _log_path
    if path is None:                      # 에이전트 재시작 뒤에도 최근 로그를 보여준다
        cands = sorted(LOGS.glob("manual_*.log")) + sorted(LOGS.glob("daily_*.log"))
        path = cands[-1] if cands else None
    if path is None or not path.exists():
        return []
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    return [ln for ln in lines if ln.strip()][-n:]


# ------------------------------------------------------------------ HTTP
class Handler(BaseHTTPRequestHandler):
    server_version = "ShortDashboardAgent/1.0"

    def log_message(self, fmt, *args):            # 기본 stderr 로깅은 시끄럽다
        pass

    # --- 공통 -------------------------------------------------------
    def _cors(self) -> None:
        origin = self.headers.get("Origin", "")
        if origin in ALLOWED_ORIGINS:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Agent-Token")
        # 공개 https 페이지 → 사설망 요청에 크롬이 요구하는 헤더
        self.send_header("Access-Control-Allow-Private-Network", "true")
        self.send_header("Access-Control-Max-Age", "600")

    def _json(self, obj, code: int = 200) -> None:
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def _authed(self) -> bool:
        token = get("AGENT_TOKEN")
        if not token:
            return True
        return self.headers.get("X-Agent-Token") == token

    # --- 라우팅 -----------------------------------------------------
    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path == "/status":
            if not self._authed():
                return self._json({"error": "unauthorized"}, 401)
            return self._json(snapshot())
        if path == "/log":
            if not self._authed():
                return self._json({"error": "unauthorized"}, 401)
            n = 40
            if "?" in self.path:
                from urllib.parse import parse_qs
                q = parse_qs(self.path.split("?", 1)[1])
                try:
                    n = max(1, min(400, int(q.get("n", ["40"])[0])))
                except ValueError:
                    pass
            return self._json({"lines": tail(n), "running": running()})
        if path == "/":
            return self._json({"ok": True, "service": "short-dashboard agent"})
        self._json({"error": "not found"}, 404)

    def do_POST(self):
        if self.path.split("?", 1)[0] != "/refresh":
            return self._json({"error": "not found"}, 404)
        if not self._authed():
            return self._json({"error": "unauthorized"}, 401)
        try:
            n = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(n) or "{}") if n else {}
        except (ValueError, OSError):
            body = {}
        days = body.get("days", 7)
        try:
            days = max(1, min(60, int(days)))
        except (TypeError, ValueError):
            days = 7
        result = start_refresh(days)
        self._json({**result, **snapshot()}, 200 if result["ok"] else 409)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1",
                    help="기본 127.0.0.1 (같은 기기에서만). LAN 개방은 0.0.0.0")
    ap.add_argument("--port", type=int, default=8766)
    a = ap.parse_args()

    srv = ThreadingHTTPServer((a.host, a.port), Handler)
    log(f"수동 갱신 에이전트 대기 → http://{a.host}:{a.port}")
    if a.host != "127.0.0.1" and not get("AGENT_TOKEN"):
        log("⚠ 외부 개방인데 AGENT_TOKEN 이 없습니다 — .env 에 설정을 권합니다.")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        log("에이전트 종료")
    finally:
        srv.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
