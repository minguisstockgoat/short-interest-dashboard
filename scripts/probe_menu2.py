# -*- coding: utf-8 -*-
"""KRX SPA 셸 페이지를 저장하고 메뉴명 ↔ menuId ↔ bld 매핑을 추출한다."""
from __future__ import annotations

import re

from common import RAW, log
from krx_session import KRX_ORIGIN, build_session

s = build_session(verify=False)
s.headers.pop("X-Requested-With", None)

path = RAW / "krx_main.html"
r = s.get(f"{KRX_ORIGIN}/contents/MDC/MDI/mdiLoader/index.cmd",
          params={"menuId": "MDC0201020403"}, timeout=40)
path.write_text(r.text, encoding="utf-8")
html = r.text
log(f"저장 {path} ({len(html):,}자)")

# 1) 공매도/대차가 들어간 메뉴 항목 주변 컨텍스트
for kw in ("공매도", "대차"):
    log(f"\n===== '{kw}' 등장 위치 =====")
    seen = set()
    for m in re.finditer(kw, html):
        seg = html[max(0, m.start() - 260): m.start() + 120]
        ids = re.findall(r"MDC\d{6,}", seg)
        names = re.findall(r">([^<>]*" + kw + r"[^<>]*)<", seg)
        if not names:
            continue
        key = (tuple(ids[-1:]), names[-1].strip())
        if key in seen:
            continue
        seen.add(key)
        log(f"  menuId={ids[-1:]}  name={names[-1].strip()!r}")

# 2) 페이지 내 bld 흔적
blds = sorted(set(re.findall(r"dbms/MDC/STAT/[\w/]+", html)))
log(f"\n페이지 내 bld {len(blds)}개: {blds[:40]}")

# 3) 외부 스크립트 목록 (bld가 번들 안에 있을 수 있음)
srcs = sorted(set(re.findall(r'src="([^"]+\.js[^"]*)"', html)))
log(f"\n스크립트 {len(srcs)}개:")
for x in srcs[:40]:
    log(f"  {x}")
