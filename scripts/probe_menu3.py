# -*- coding: utf-8 -*-
"""메뉴 링크 마크업을 보고 화면 콘텐츠 로딩 방식을 파악한다."""
import re

from common import RAW

h = (RAW / "krx_main.html").read_text(encoding="utf-8")
for mid in ("MDC02030301", "MDC02030201", "MDC02030501"):
    i = h.find(mid)
    print(f"\n===== {mid} (offset {i}) =====")
    print(h[max(0, i - 600): i + 300].replace("\r", ""))

print("\n===== 화면 로딩 관련 함수/URL 후보 =====")
for pat in [r"/contents/MDC/[\w/]+\.(?:cmd|jsp|do)", r"function\s+goMenu\w*\([^)]*\)",
            r"mdiLoader[^\"']{0,80}", r"\.cmd\?[\w=&]{0,60}"]:
    hits = sorted(set(re.findall(pat, h)))[:20]
    print(f"{pat} -> {hits}")
