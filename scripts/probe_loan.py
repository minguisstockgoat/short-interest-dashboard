# -*- coding: utf-8 -*-
"""대차거래 관련 bld(31101~31401 추정)를 확정하고 종목별 잔고 제공 여부를 확인한다."""
from __future__ import annotations

import json

from common import log
from krx_session import JSON_URL, build_session

s = build_session(verify=False)
ISIN, D0, D1 = "KR7005930003", "20260601", "20260728"
COMMON = {"locale": "ko_KR", "share": "1", "money": "1", "csvxls_isNo": "false"}

BLDS = [f"dbms/MDC/STAT/srt/MDCSTAT{n}" for n in
        (30601, 30701, 30801, 31101, 31201, 31301, 31401, 31501)]

VAR = {
    "T1 전종목/일자": {"searchType": "1", "mktTpCd": "1", "mktId": "STK",
                    "trdDd": D1, "strtDd": D0, "endDd": D1},
    "T2 개별/기간": {"searchType": "2", "mktTpCd": "1", "mktId": "STK",
                  "isuCd": ISIN, "trdDd": D1, "strtDd": D0, "endDd": D1},
    "T0 기간만": {"mktTpCd": "1", "mktId": "STK",
                "trdDd": D1, "strtDd": D0, "endDd": D1},
}

for bld in BLDS:
    for vn, v in VAR.items():
        try:
            r = s.post(JSON_URL, data={**COMMON, **v, "bld": bld}, timeout=60)
            js = r.json()
        except Exception:
            continue
        key = next((k for k in js if isinstance(js[k], list) and js[k]), None)
        if not key:
            continue
        rows = js[key]
        log(f"✅ {bld} [{vn}] {len(rows)}행")
        log(f"    cols: {list(rows[0].keys())}")
        log(f"    row0: {json.dumps(rows[0], ensure_ascii=False)[:320]}")
        break
    else:
        log(f"·  {bld} 응답 없음")
