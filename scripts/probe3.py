"""Matrix probe: find a request shape data.krx.co.kr accepts; also test OPEN API reachability."""
import os
import requests

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/125.0 Safari/537.36")
PAYLOAD = {
    "bld": "dbms/MDC/STAT/standard/MDCSTAT01501",
    "locale": "ko_KR", "mktId": "ALL", "trdDd": "20260728",
    "share": "1", "money": "1", "csvxls_isNo": "false",
}


def try_case(name, scheme, boot, headers):
    s = requests.Session()
    s.headers.update({"User-Agent": UA, "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8"})
    try:
        if boot:
            b = s.get(f"{scheme}://data.krx.co.kr{boot}", timeout=20)
            bs = b.status_code
        else:
            bs = "-"
        r = s.post(f"{scheme}://data.krx.co.kr/comm/bldAttendant/getJsonData.cmd",
                   data=PAYLOAD, headers=headers, timeout=25)
        print(f"{name:52s} boot={bs} post={r.status_code} body={r.text[:60]!r}")
    except Exception as e:
        print(f"{name:52s} ERROR {e!r}")


CT = {"Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"}
REF = {"Referer": "https://data.krx.co.kr/contents/MDC/MDI/mdiLoader/index.cmd?menuId=MDC0201020101"}
XHR = {"X-Requested-With": "XMLHttpRequest"}

try_case("A https, no boot, UA only", "https", None, {})
try_case("B https, no boot, CT", "https", None, CT)
try_case("C https, boot root, CT+REF+XHR", "https", "/", {**CT, **REF, **XHR})
try_case("D https, boot mdiLoader, CT+REF+XHR", "https",
         "/contents/MDC/MDI/mdiLoader/index.cmd?menuId=MDC0201020101", {**CT, **REF, **XHR})
try_case("E http, boot root, CT+REF", "http", "/", {**CT, **REF})
try_case("F https, boot MDC main, CT+REF+XHR", "https", "/contents/MDC/MDI/mainIndex.cmd", {**CT, **REF, **XHR})

print("\n--- OPEN API reachability ---")
key = os.environ.get("KRX_API_KEY", "")
for path in ["sto/stk_bydd_trd"]:
    r = requests.get(f"https://data-dbg.krx.co.kr/svc/apis/{path}",
                     params={"basDd": "20260728"},
                     headers={"AUTH_KEY": key}, timeout=30)
    print(path, r.status_code, r.text[:200])
