# -*- coding: utf-8 -*-
"""KOFIA FreeSIS 대차거래 API 구조를 확인한다 (로그인 불필요).

캡처된 요청
  종목검색 : POST /app/businessSearch/statComBusinessSearchBO.do
             {"dmBusinessSearch":{"tmpV2":"<검색어>","tmpV1":"1"}}
  데이터   : POST /meta/getMetaDataList.do
             {"dmSearch":{"tmpV1":"D","tmpV45":"<시작>","tmpV46":"<종료>",
                          "tmpV72":"<종목?>","OBJ_NM":"STATSCU0100000140BO"}}
"""
from __future__ import annotations

import json

import requests

BASE = "https://freesis.kofia.or.kr"
H = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"),
    "Content-Type": "application/json;charset=UTF-8",
    "Referer": f"{BASE}/stat/FreeSIS.do",
    "Accept": "application/json, text/plain, */*",
}
s = requests.Session()
s.headers.update(H)


def post(path, payload):
    r = s.post(BASE + path, data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
               timeout=30)
    txt = r.text
    if not txt.strip().startswith("{"):
        return {"_raw": txt[:200], "_status": r.status_code}
    return r.json()


print("===== 1. 종목 검색 =====")
for q in ["삼성전자", "SK하이닉스", "하이닉스", "005930"]:
    js = post("/app/businessSearch/statComBusinessSearchBO.do",
              {"dmBusinessSearch": {"tmpV2": q, "tmpV1": "1"}})
    keys = [k for k in js if k != "_raw"]
    rows = None
    for k in keys:
        v = js[k]
        if isinstance(v, list) and v:
            rows = v
            print(f"  '{q}' → {k}: {len(v)}건")
            for r0 in v[:4]:
                print(f"      {json.dumps(r0, ensure_ascii=False)[:200]}")
            break
    if rows is None:
        print(f"  '{q}' → {json.dumps(js, ensure_ascii=False)[:220]}")

print("\n===== 2. 대차거래 데이터 (STATSCU0100000140) =====")
for label, extra in [("tmpV72 비움(전체?)", {"tmpV72": ""}),
                     ("tmpV72=005930", {"tmpV72": "005930"}),
                     ("tmpV72=000660", {"tmpV72": "000660"})]:
    js = post("/meta/getMetaDataList.do",
              {"dmSearch": {"tmpV40": "1000000", "tmpV41": "1", "tmpV1": "D",
                            "tmpV45": "20260701", "tmpV46": "20260730",
                            "OBJ_NM": "STATSCU0100000140BO", **extra}})
    shown = False
    for k, v in js.items():
        if isinstance(v, list) and v:
            print(f"  [{label}] {k}: {len(v)}건")
            print(f"      cols: {list(v[0].keys())}")
            for r0 in v[:3]:
                print(f"      {json.dumps(r0, ensure_ascii=False)[:260]}")
            shown = True
            break
    if not shown:
        print(f"  [{label}] 빈 응답: {json.dumps(js, ensure_ascii=False)[:220]}")
