# -*- coding: utf-8 -*-
"""CDP에 붙어있는 탭 목록을 출력한다."""
import json
import urllib.request

with urllib.request.urlopen("http://127.0.0.1:9222/json", timeout=5) as r:
    ts = json.load(r)
for i, t in enumerate(ts):
    if t.get("type") != "page":
        continue
    print(f"[{i}] {t.get('title','')[:60]}")
    print(f"     {t.get('url','')[:130]}")
