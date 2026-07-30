"""Probe data.krx.co.kr short-selling JSON endpoints to discover working bld codes/params."""
import json
import sys

import requests

URL = "https://data.krx.co.kr/comm/bldAttendant/getJsonData.cmd"
LOADER = "https://data.krx.co.kr/contents/MDC/MDI/mdiLoader/index.cmd"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0 Safari/537.36",
    "Referer": "https://data.krx.co.kr/contents/MDC/MDI/mdiLoader/index.cmd?menuId=MDC0201020403",
    "X-Requested-With": "XMLHttpRequest",
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Origin": "https://data.krx.co.kr",
}

TRD_DD = sys.argv[1] if len(sys.argv) > 1 else "20260728"

CASES = [
    # (label, payload)
    ("30101 종목별 공매도 거래 (전종목/일자)", {
        "bld": "dbms/MDC/STAT/srt/MDCSTAT30101",
        "mktId": "STK", "trdDd": TRD_DD, "inqCondTpCd": "1",
        "share": "1", "money": "1", "csvxls_isNo": "false",
    }),
    ("30401 개별종목 공매도 잔고 (전종목/일자)", {
        "bld": "dbms/MDC/STAT/srt/MDCSTAT30401",
        "mktTpCd": "1", "trdDd": TRD_DD,
        "share": "1", "money": "1", "csvxls_isNo": "false",
    }),
    ("30501 공매도 잔고 상위 50", {
        "bld": "dbms/MDC/STAT/srt/MDCSTAT30501",
        "mktTpCd": "1", "trdDd": TRD_DD,
        "share": "1", "money": "1", "csvxls_isNo": "false",
    }),
    ("30301 공매도 거래 상위 50", {
        "bld": "dbms/MDC/STAT/srt/MDCSTAT30301",
        "mktId": "STK", "trdDd": TRD_DD, "inqCondTpCd": "1",
        "share": "1", "money": "1", "csvxls_isNo": "false",
    }),
    ("30001 공매도 종합", {
        "bld": "dbms/MDC/STAT/srt/MDCSTAT30001",
        "mktId": "STK", "trdDd": TRD_DD,
        "share": "1", "money": "1", "csvxls_isNo": "false",
    }),
]

sess = requests.Session()
sess.headers.update({"User-Agent": HEADERS["User-Agent"]})
boot = sess.get(LOADER, params={"menuId": "MDC0201020403"}, timeout=20)
print(f"[boot] HTTP {boot.status_code} cookies={sess.cookies.get_dict().keys()}")

for label, payload in CASES:
    try:
        r = sess.post(URL, data=payload, headers=HEADERS, timeout=20)
        body = r.text
        try:
            js = r.json()
        except Exception:
            print(f"--- {label}: HTTP {r.status_code} NON-JSON: {body[:200]!r}")
            continue
        keys = list(js.keys())
        blockkey = next((k for k in keys if isinstance(js[k], list)), None)
        rows = js.get(blockkey) or []
        print(f"--- {label}: HTTP {r.status_code} keys={keys} n={len(rows)}")
        if rows:
            print("    cols:", list(rows[0].keys()))
            print("    row0:", json.dumps(rows[0], ensure_ascii=False))
    except Exception as e:
        print(f"--- {label}: ERROR {e!r}")
