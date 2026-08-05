# -*- coding: utf-8 -*-
"""KRX 로그인용 크롬(원격 디버깅 9222) 기동·점검 — Windows/macOS 공통.

전용 프로필(.chrome-profile)을 쓰므로 평소 쓰는 크롬 창과 섞이지 않는다.
프로필에 쿠키가 남으므로 크롬을 다시 띄우면 로그인이 유지되는 경우가 많고,
풀렸으면 krx_login.py 가 이 창을 로그인 페이지로 띄운 뒤 사람에게 네이버
로그인을 요청한다(KRX는 네이버 SSO라 비밀번호 자동 입력을 하지 않는다).
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


def new_tab(url: str = LOGIN_URL, *, wait: float = 2.0) -> bool:
    """탭을 하나 연다. 최신 크롬은 /json/new 에 PUT 을 요구한다."""
    req = urllib.request.Request(f"{CDP_HOST}/json/new?{url}", method="PUT")
    try:
        with urllib.request.urlopen(req, timeout=10):
            pass
    except Exception as e:
        log(f"탭 열기 실패: {type(e).__name__} {e}")
        return False
    time.sleep(wait)                 # 타겟 목록에 잡힐 여유
    return True


def ensure_page(url: str = LOGIN_URL) -> bool:
    """페이지 탭이 최소 하나 있도록 한다.

    맥은 창을 모두 닫아도 크롬 프로세스가 살아남는다. 그러면 9222 는 응답하는데
    page 타겟이 0개라 쿠키를 읽을 대상이 없다 — 세션이 죽은 게 아니라 창만 없는
    상태이므로, 탭을 하나 열어주면 그대로 이어서 쓸 수 있다.
    """
    if not cdp_up():
        return False
    try:
        if any(t.get("type") == "page" for t in targets()):
            return True
    except Exception:
        return False
    log("크롬에 페이지 탭이 없습니다 — 탭을 하나 엽니다.")
    return new_tab(url)


def _prefer_session_restore() -> None:
    """프로필에 '이전 세션 복원'을 켜둔다 (크롬이 꺼져 있을 때만 호출할 것).

    KRX 로그인 쿠키(mdc.client_session)는 브라우저 세션 쿠키라 브라우징 세션이
    끝나면 사라진다. 복원을 켜두면 크롬을 다시 띄울 때 세션 쿠키까지 살아나
    재로그인 없이 이어진다. exit_type 도 정상으로 돌려 복구 풍선을 막는다.
    """
    pref = PROFILE / "Default" / "Preferences"
    if not pref.exists():
        return
    try:
        d = json.loads(pref.read_text(encoding="utf-8"))
        d.setdefault("session", {})["restore_on_startup"] = 1   # 1 = 이전 세션 복원
        d.setdefault("profile", {})["exit_type"] = "Normal"
        pref.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    except (OSError, ValueError) as e:
        log(f"프로필 설정 조정 실패(무시하고 진행): {type(e).__name__} {e}")


def launch(*, wait: float = 25.0, url: str = LOGIN_URL) -> bool:
    """크롬이 안 떠 있으면 띄우고 9222 가 열릴 때까지 기다린다.

    맥미니는 화면이 잠겨 있어도 launchd 세션에서 창을 띄울 수 있다. GUI 세션이
    없는 환경(SSH만 붙은 상태 등)에서는 실패할 수 있으므로 반환값으로 알린다.
    """
    if cdp_up():
        return True

    exe = chrome_path()
    PROFILE.mkdir(parents=True, exist_ok=True)
    _prefer_session_restore()
    args = [
        exe,
        "--remote-debugging-port=9222",
        "--remote-allow-origins=*",
        f"--user-data-dir={PROFILE}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-session-crashed-bubble",
        # --restore-last-session=false 는 쓰지 않는다. 그 플래그가 세션 쿠키까지
        # 버려서, 크롬을 다시 띄울 때마다 KRX 재로그인을 요구하게 만든다.
        "--restore-last-session",
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
