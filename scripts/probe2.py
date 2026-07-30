"""Second probe: verify whether the getJsonData mechanism works at all with a known bld."""
import json
import requests

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/125.0 Safari/537.36")
URL = "https://data.krx.co.kr/comm/bldAttendant/getJsonData.cmd"

s = requests.Session()
s.headers.update({"User-Agent": UA})
s.get("https://data.krx.co.kr/contents/MDC/MDI/mdiLoader/index.cmd",
      params={"menuId": "MDC0201020101"}, timeout=20)

TESTS = [
    ("전종목시세 MDCSTAT01501", {
        "bld": "dbms/MDC/STAT/standard/MDCSTAT01501",
        "locale": "ko_KR", "mktId": "ALL", "trdDd": "20260728",
        "share": "1", "money": "1", "csvxls_isNo": "false"}),
    ("공매도잔고 30401 +locale", {
        "bld": "dbms/MDC/STAT/srt/MDCSTAT30401",
        "locale": "ko_KR", "mktTpCd": "1", "trdDd": "20260728",
        "share": "1", "money": "1", "csvxls_isNo": "false"}),
    ("전종목시세 without locale", {
        "bld": "dbms/MDC/STAT/standard/MDCSTAT01501",
        "mktId": "ALL", "trdDd": "20260728",
        "share": "1", "money": "1", "csvxls_isNo": "false"}),
]

for label, payload in TESTS:
    r = s.post(URL, data=payload, headers={
        "Referer": "https://data.krx.co.kr/contents/MDC/MDI/mdiLoader/index.cmd",
        "X-Requested-With": "XMLHttpRequest",
        "Origin": "https://data.krx.co.kr",
    }, timeout=25)
    txt = r.text
    print(f"--- {label}: HTTP {r.status_code} len={len(txt)}")
    if txt.startswith("{"):
        js = json.loads(txt)
        bk = next((k for k in js if isinstance(js[k], list)), None)
        rows = js.get(bk) or []
        print(f"    block={bk} n={len(rows)}")
        if rows:
            print("    cols:", list(rows[0].keys()))
    else:
        print("    body:", txt[:300])
