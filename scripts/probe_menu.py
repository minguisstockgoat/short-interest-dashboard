# -*- coding: utf-8 -*-
"""로그인 세션으로 KRX 메뉴 트리를 받아 '공매도'/'대차' 화면의 menuId와 bld를 찾는다."""
from __future__ import annotations

import json
import re

from common import log
from krx_session import KRX_ORIGIN, build_session

s = build_session(verify=False)
s.headers.pop("X-Requested-With", None)

# 1) 메뉴 트리 후보 엔드포인트
for path, method in [("/comm/menu/getMenuList.cmd", "post"),
                     ("/comm/menu/getMenuTree.cmd", "post"),
                     ("/contents/COM/GenerateOTP.jspx", "get"),
                     ("/comm/menuTree/getMenuTree.cmd", "post")]:
    try:
        r = getattr(s, method)(KRX_ORIGIN + path, timeout=20)
        log(f"{path} -> {r.status_code} len={len(r.text)} head={r.text[:90]!r}")
    except Exception as e:
        log(f"{path} -> ERR {e!r}")

# 2) 메인 페이지에서 menuId 수집
r = s.get(f"{KRX_ORIGIN}/contents/MDC/MAIN/main/index.cmd", timeout=25)
log(f"main page {r.status_code} len={len(r.text)}")
menu_ids = sorted(set(re.findall(r"MDC\d{6,}", r.text)))
log(f"main page menuId 후보 {len(menu_ids)}개: {menu_ids[:25]}")

# 3) 메뉴별 로더 페이지에서 bld 추출
hits = {}
for mid in menu_ids:
    try:
        rr = s.get(f"{KRX_ORIGIN}/contents/MDC/MDI/mdiLoader/index.cmd",
                   params={"menuId": mid}, timeout=20)
    except Exception:
        continue
    body = rr.text
    blds = sorted(set(re.findall(r"dbms/MDC/STAT/[\w/]+", body)))
    title = re.findall(r"<title>([^<]*)</title>", body)
    names = sorted(set(re.findall(r"[가-힣][가-힣\s·/()]{2,20}", body)))
    if blds:
        hits[mid] = {"title": title[:1], "blds": blds}
        log(f"  {mid} len={len(body)} blds={blds}")
    elif len(body) > 1200:
        log(f"  {mid} len={len(body)} title={title[:1]} 한글={names[:6]}")

print("\n===== menuId -> bld =====")
print(json.dumps(hits, ensure_ascii=False, indent=1))
