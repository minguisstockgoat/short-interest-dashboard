# -*- coding: utf-8 -*-
"""텔레그램 알림.

무인 실행이라 실패가 조용히 묻히는 게 가장 큰 문제였다. 사람이 개입해야만
풀리는 상황(KRX 로그인 실패·잠금 위험·데이터 지연)만 골라서 보낸다.

  .env
    TELEGRAM_BOT_TOKEN=123456:AA...
    TELEGRAM_CHAT_ID=123456789

설정이 없으면 조용히 건너뛰되 로그에는 남긴다 — 알림 미설정 자체로 파이프라인을
멈추지는 않는다.

같은 사유의 알림이 매 실행마다 반복되지 않도록 dedupe key 별 쿨다운을 둔다.
"""
from __future__ import annotations

import datetime as dt
import json
import urllib.parse
import urllib.request

from common import DATA, log
from envfile import get

API = "https://api.telegram.org/bot{token}/sendMessage"
STATE = DATA / ".notify_state.json"
DEFAULT_COOLDOWN_H = 6


def _state() -> dict:
    if STATE.exists():
        try:
            return json.loads(STATE.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            pass
    return {}


def _save(s: dict) -> None:
    try:
        STATE.write_text(json.dumps(s, ensure_ascii=False, indent=1),
                         encoding="utf-8")
    except OSError:
        pass


def configured() -> bool:
    return bool(get("TELEGRAM_BOT_TOKEN") and get("TELEGRAM_CHAT_ID"))


def send(text: str, *, dedupe: str | None = None,
         cooldown_h: float = DEFAULT_COOLDOWN_H) -> bool:
    """텔레그램으로 보낸다. 보냈으면 True.

    dedupe 를 주면 같은 키의 알림을 cooldown_h 시간 안에는 다시 보내지 않는다.
    """
    token, chat = get("TELEGRAM_BOT_TOKEN"), get("TELEGRAM_CHAT_ID")
    if not (token and chat):
        log("텔레그램 미설정 — 알림 생략 (.env 의 TELEGRAM_BOT_TOKEN/CHAT_ID)")
        return False

    now = dt.datetime.now()
    st = _state()
    if dedupe:
        last = st.get(dedupe)
        if last:
            try:
                gap = (now - dt.datetime.fromisoformat(last)).total_seconds()
                if gap < cooldown_h * 3600:
                    log(f"알림 억제({dedupe}) — {gap/3600:.1f}h 전에 이미 발송")
                    return False
            except ValueError:
                pass

    body = urllib.parse.urlencode({
        "chat_id": chat,
        "text": f"[공매도 대시보드]\n{text}",
        "disable_web_page_preview": "true",
    }).encode()

    try:
        req = urllib.request.Request(API.format(token=token), data=body)
        with urllib.request.urlopen(req, timeout=15) as r:
            ok = json.load(r).get("ok", False)
    except Exception as e:                       # 알림 실패가 파이프라인을 죽이면 안 된다
        log(f"텔레그램 전송 실패: {type(e).__name__} {e}")
        return False

    if ok and dedupe:
        st[dedupe] = now.isoformat(timespec="seconds")
        _save(st)
    log(f"텔레그램 알림 발송{'' if ok else ' 실패(ok=false)'}: {text.splitlines()[0][:50]}")
    return bool(ok)


def clear(dedupe: str) -> None:
    """상황이 해소됐을 때 쿨다운을 지워 다음 발생 시 즉시 알리도록 한다."""
    st = _state()
    if st.pop(dedupe, None) is not None:
        _save(st)


if __name__ == "__main__":
    import sys
    msg = " ".join(sys.argv[1:]) or "테스트 알림입니다. 이 메시지가 보이면 설정 완료."
    sys.exit(0 if send(msg) else 1)
