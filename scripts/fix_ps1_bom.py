# -*- coding: utf-8 -*-
"""모든 .ps1 파일을 UTF-8 BOM으로 저장한다.

Windows PowerShell 5.1은 BOM이 없으면 .ps1 을 시스템 ANSI 코드페이지로 읽는다.
한글 주석/문자열이 깨지면서 따옴표·괄호 짝이 어긋나 파싱 오류가 난다.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BOM = b"\xef\xbb\xbf"

for p in sorted(ROOT.glob("*.ps1")):
    raw = p.read_bytes()
    if raw.startswith(BOM):
        print(f"  = {p.name} (이미 BOM)")
        continue
    text = raw.decode("utf-8")
    p.write_bytes(BOM + text.encode("utf-8"))
    print(f"  + {p.name} BOM 추가")
print("완료")
