# -*- coding: utf-8 -*-
"""bld 메타정보(getBldInfo.cmd)를 조회해 화면 한글명으로 공매도/대차 bld를 특정한다."""
from __future__ import annotations

import json
import re
import sys

from common import log
from krx_session import KRX_ORIGIN, build_session

BLDINFO = f"{KRX_ORIGIN}/comm/bldAttendant/getBldInfo.cmd"

s = build_session(verify=False)

groups = {
    "srt": list(range(30001, 31500, 100)) + [n + 1 for n in range(30000, 31400, 100)],
    "standard": [10501, 10601, 10701, 21501, 21601, 21701],
}
KEYWORDS = ("공매도", "대차", "잔고", "차입")

found = []
for grp, nums in groups.items():
    for n in sorted(set(nums)):
        bld = f"dbms/MDC/STAT/{grp}/MDCSTAT{n}"
        try:
            r = s.get(BLDINFO, params={"bld": bld}, timeout=25)
            t = r.text.strip()
            if not t.startswith("{"):
                continue
            js = json.loads(t)
        except Exception:
            continue
        blob = json.dumps(js, ensure_ascii=False)
        title = js.get("bldNm") or js.get("title") or ""
        if not title:
            m = re.search(r'"(?:bldNm|scrnNm|menuNm)"\s*:\s*"([^"]+)"', blob)
            title = m.group(1) if m else ""
        if title:
            hit = any(k in title for k in KEYWORDS)
            log(f"{'★' if hit else ' '} {bld}  {title}")
            found.append({"bld": bld, "title": title,
                          "inputs": [f.get("id") or f.get("name")
                                     for f in (js.get("inputs") or js.get("param") or [])][:14]})
sys.stdout.flush()
print("\n===== 공매도/대차 관련 =====")
for f in found:
    if any(k in f["title"] for k in KEYWORDS):
        print(json.dumps(f, ensure_ascii=False))
