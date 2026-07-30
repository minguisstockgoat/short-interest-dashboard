# -*- coding: utf-8 -*-
"""공매도 순보유잔고/거래, 대차거래 bld를 실제 파라미터로 확정한다."""
from __future__ import annotations

import json

from common import log
from krx_session import JSON_URL, build_session

s = build_session(verify=False)

ISIN = "KR7005930003"      # 삼성전자
SHORT = "005930"
D0, D1 = "20260601", "20260729"

BLDS = [f"dbms/MDC/STAT/srt/MDCSTAT{n}" for n in
        (30001, 30101, 30201, 30501, 30601, 30701, 30801,
         31101, 31201, 31301, 31401, 31501)]

VARIANTS = {
    "A 개별종목(ISIN)+기간": {
        "isuCd": ISIN, "isuCd2": ISIN, "strtDd": D0, "endDd": D1,
        "tboxisuCd_finder_srtisu0_0": f"{SHORT}/삼성전자",
        "codeNmisuCd_finder_srtisu0_0": "삼성전자",
        "param1isuCd_finder_srtisu0_0": "ALL",
        "mktTpCd": "1", "mktId": "STK", "inqCondTpCd": "1", "inqTpCd": "1",
    },
    "B 전종목+단일일자": {
        "trdDd": D1, "mktTpCd": "1", "mktId": "STK",
        "inqCondTpCd": "2", "inqTpCd": "2", "secugrpId": "STMFRTSCIFDRFS",
    },
    "C 전종목+기간": {
        "strtDd": D1, "endDd": D1, "trdDd": D1,
        "mktTpCd": "1", "mktId": "STK", "inqCondTpCd": "2", "inqTpCd": "2",
    },
}
COMMON = {"locale": "ko_KR", "share": "1", "money": "1", "csvxls_isNo": "false"}

for bld in BLDS:
    for vname, v in VARIANTS.items():
        p = {**COMMON, **v, "bld": bld}
        try:
            r = s.post(JSON_URL, data=p, timeout=45)
            t = r.text.strip()
            if not t.startswith("{"):
                continue
            js = json.loads(t)
            key = next((k for k in js if isinstance(js[k], list) and js[k]), None)
            if not key:
                continue
            rows = js[key]
            log(f"✅ {bld} [{vname}] {len(rows)}행")
            log(f"     cols: {list(rows[0].keys())}")
            log(f"     row0: {json.dumps(rows[0], ensure_ascii=False)[:300]}")
            break
        except Exception as e:
            log(f"   {bld} [{vname}] ERR {e!r}")
