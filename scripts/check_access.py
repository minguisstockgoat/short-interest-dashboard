# -*- coding: utf-8 -*-
"""KRX 접속 가능 여부를 최소 요청으로 1회만 확인한다 (수집 금지)."""
from __future__ import annotations

import requests

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")

for name, url in [
    ("data.krx.co.kr 메인", "https://data.krx.co.kr/contents/MDC/MAIN/main/index.cmd"),
    ("krx.co.kr 홈", "https://www.krx.co.kr/main/main.jsp"),
    ("OPEN API(data-dbg)", "https://data-dbg.krx.co.kr/svc/apis/sto/stk_bydd_trd"),
]:
    try:
        r = requests.get(url, headers={"User-Agent": UA}, timeout=15)
        body = r.text[:120].replace("\n", " ").replace("\r", "")
        print(f"{name:22s} HTTP {r.status_code}  len={len(r.text):,}  {body[:90]!r}")
    except Exception as e:
        print(f"{name:22s} ERROR {type(e).__name__}: {str(e)[:110]}")
