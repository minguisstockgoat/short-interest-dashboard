# -*- coding: utf-8 -*-
"""캡처된 파라미터(searchType 포함)로 공매도 잔고/거래 조회 모드를 확정한다."""
from __future__ import annotations

import json

from common import log
from krx_session import JSON_URL, build_session

s = build_session(verify=False)
ISIN, D0, D1 = "KR7005930003", "20260601", "20260729"

CASES = [
    ("잔고 30501 searchType=1 (전종목/일자)", {
        "bld": "dbms/MDC/STAT/srt/MDCSTAT30501", "searchType": "1",
        "mktTpCd": "1", "trdDd": D1, "strtDd": D0, "endDd": D1}),
    ("잔고 30501 searchType=2 (개별/기간)", {
        "bld": "dbms/MDC/STAT/srt/MDCSTAT30501", "searchType": "2",
        "mktTpCd": "1", "isuCd": ISIN, "trdDd": D1, "strtDd": D0, "endDd": D1}),
    ("거래 30101 searchType=1 (전종목/일자)", {
        "bld": "dbms/MDC/STAT/srt/MDCSTAT30101", "searchType": "1",
        "mktId": "STK", "secugrpId": "STMFRTSCIFDRFS",
        "inqCond": "STMFRTSCIFDRFSSRSWBC", "trdDd": D1, "strtDd": D0, "endDd": D1}),
    ("거래 30101 searchType=2 (개별/기간)", {
        "bld": "dbms/MDC/STAT/srt/MDCSTAT30101", "searchType": "2",
        "mktId": "STK", "isuCd": ISIN, "secugrpId": "STMFRTSCIFDRFS",
        "trdDd": D1, "strtDd": D0, "endDd": D1}),
]
COMMON = {"locale": "ko_KR", "share": "1", "money": "1", "csvxls_isNo": "false"}

for name, p in CASES:
    r = s.post(JSON_URL, data={**COMMON, **p}, timeout=60)
    t = r.text.strip()
    if not t.startswith("{"):
        log(f"❌ {name}: {t[:60]}")
        continue
    js = json.loads(t)
    key = next((k for k in js if isinstance(js[k], list) and js[k]), None)
    if not key:
        log(f"⚠  {name}: 빈 응답 keys={list(js.keys())}")
        continue
    rows = js[key]
    log(f"✅ {name}: {len(rows)}행")
    log(f"    cols: {list(rows[0].keys())}")
    log(f"    row0: {json.dumps(rows[0], ensure_ascii=False)[:340]}")
    log(f"    rowN: {json.dumps(rows[-1], ensure_ascii=False)[:340]}")
