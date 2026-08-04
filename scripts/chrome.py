# -*- coding: utf-8 -*-
"""KRX 로그인용 크롬(원격 디버깅 9222) 기동·점검 — Windows/macOS 공통.

전용 프로필(.chrome-profile)을 쓰므로 평소 쓰는 크롬 창과 섞이지 않는다.
프로필에 쿠키가 남으므로 크롬을 다시 띄우면 로그인이 유지되는 경우가 많고,
풀렸으면 krx_login.py 가 .env 계정으로 다시 로그인한다.
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from common import ROOT, log

CDP_HOST = "http://127.0.0.1:9222"
PROFILE = ROOT / ".chrome-profile"
LOGIN_URL = "https://data.krx.co.kr/contents/MDC/COMS/client/MDCCOMS001.cmd"

_CANDIDATES = {
    "win32": [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        str(Path.home() / r"AppData\Local\Google\Chrome\Application\chrome.exe"),
    ],
    "darwin": [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        str(Path.home() / "Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
    ],
    "linux": ["/usr/bin/google-chrome", "/usr/bin/chromium-browser", "/usr/bin/chromium"],
}


def chrome_path() -> str:
    for p in _CANDIDATES.get(sys.platform, _CANDIDATES["linux"]):
        if Path(p).exists():
            return p
    raise SystemExit("크롬 실행 파일을 찾지 못했습니다. 설치 경로를 확인하세요.")


def cdp_up(timeout: float = 3.0) -> bool:
    """9222 가 응답하는지."""
    try:
        with urllib.request.urlopen(f"{CDP_HOST}/json/version", timeout=timeout):
            return True
    except Exception:
        return False


def targets() -> list[dict]:
    with urllib.request.urlopen(f"{CDP_HOST}/json", timeout=5) as r:
        return json.load(r)


def launch(*, wait: float = 25.0, url: str = LOGIN_URL) -> bool:
    """크롬이 안 떠 있으면 띄우고 9222 가 열릴 때까지 기다린다.

    맥미니는 화면이 잠겨 있어도 launchd 세션에서 창을 띄울 수 있다. GUI 세션이
    없는 환경(SSH만 붙은 상태 등)에서는 실패할 수 있으므로 반환값으로 알린다.
    """
    if cdp_up():
        return True

    exe = chrome_path()
    PROFILE.mkdir(parents=True, exist_ok=True)
    args = [
        exe,
        "--remote-debugging-port=9222",
        "--remote-allow-origins=*",
        f"--user-data-dir={PROFILE}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-session-crashed-bubble",
        "--restore-last-session=false",
        url,
    ]
    log(f"크롬 기동: {exe}")
    kw: dict = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
    if sys.platform == "win32":
        kw["creationflags"] = getattr(subprocess, "DETACHED_PROCESS", 0)
    else:
        kw["start_new_session"] = True
    subprocess.Popen(args, **kw)

    deadline = time.time() + wait
    while time.time() < deadline:
        if cdp_up():
            time.sleep(1.5)          # 첫 탭이 붙을 여유
            log("크롬 원격 디버깅 연결됨 (9222)")
            return True
        time.sleep(0.7)
    log(f"크롬을 {wait:.0f}초 안에 띄우지 못했습니다.")
    return False


if __name__ == "__main__":
    ok = launch()
    print("✅ 크롬 준비됨" if ok else "❌ 크롬 기동 실패")
    sys.exit(0 if ok else 1)
