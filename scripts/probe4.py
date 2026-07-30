"""Probe A: inspect KRX data page HTML for the real ajax endpoint.
Probe B: hunt for a short-selling service on the OPEN API host."""
import os
import re
import requests

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/125.0 Safari/537.36")
s = requests.Session()
s.headers.update({"User-Agent": UA})

print("=== A. mdiLoader page HTML ===")
r = s.get("https://data.krx.co.kr/contents/MDC/MDI/mdiLoader/index.cmd",
          params={"menuId": "MDC0201020403"}, timeout=25)
html = r.text
print("status", r.status_code, "len", len(html))
for pat in [r'[\w/\.]*getJsonData[\w\.]*', r'MDCSTAT\d+', r'bldAttendant[\w/\.]*',
            r'/comm/[\w/\.]+\.cmd', r'dbms/MDC/[\w/]+']:
    hits = sorted(set(re.findall(pat, html)))[:12]
    print(f"  {pat}: {hits}")

print("\n=== B. OPEN API short-selling path hunt ===")
key = os.environ.get("KRX_API_KEY", "")
cands = [
    "sto/srt_bydd_trd", "sto/stk_srt_bydd_trd", "sto/ksq_srt_bydd_trd",
    "srt/stk_bydd_trd", "sto/stk_srt_bal", "sto/short_bydd_trd",
    "sto/stk_shortsell", "sto/stk_srtsl_trd",
]
for p in cands:
    try:
        rr = requests.get(f"https://data-dbg.krx.co.kr/svc/apis/{p}",
                          params={"basDd": "20260728"},
                          headers={"AUTH_KEY": key}, timeout=20)
        print(f"  {p:26s} {rr.status_code} {rr.text[:110]!r}")
    except Exception as e:
        print(f"  {p:26s} ERR {e!r}")
