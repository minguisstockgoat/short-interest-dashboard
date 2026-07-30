# -*- coding: utf-8 -*-
"""공매도 순보유잔고(MDCSTAT30501) 조회 조건을 확정한다 (공시 시차 탐색)."""
from __future__ import annotations

import json

from common import log
from krx_session import JSON_URL, build_session

s = build_session(verify=False)
COMMON = {"locale": "ko_KR", "share": "1", "money": "1", "csvxls_isNo": "false",
          "bld": "dbms/MDC/STAT/srt/MDCSTAT30501"}

DATES = ["20260729", "20260728", "20260727", "20260724", "20260723",
         "20260722", "20260721", "20260717", "20260710"]

log("--- searchType=1, mktTpCd=1 (KOSPI), 날짜별 ---")
for d in DATES:
    r = s.post(JSON_URL, data={**COMMON, "searchType": "1", "mktTpCd": "1",
                               "trdDd": d, "strtDd": d, "endDd": d}, timeout=60)
    try:
        js = r.json()
    except Exception:
        log(f"  {d}: 비JSON {r.text[:40]}")
        continue
    rows = js.get("OutBlock_1") or []
    log(f"  {d}: {len(rows)}행" + (f"  cols={list(rows[0].keys())}" if rows else ""))
    if rows:
        log(f"      row0: {json.dumps(rows[0], ensure_ascii=False)[:340]}")
        break

log("--- mktTpCd 변형 (기준일 20260727) ---")
for mkt in ["1", "2", "3", "0", "ALL", "STK", "KSQ"]:
    r = s.post(JSON_URL, data={**COMMON, "searchType": "1", "mktTpCd": mkt,
                               "trdDd": "20260727", "strtDd": "20260727",
                               "endDd": "20260727"}, timeout=60)
    try:
        n = len(r.json().get("OutBlock_1") or [])
    except Exception:
        n = -1
    log(f"  mktTpCd={mkt}: {n}행")
