"""Probe login-free sources for 공매도 잔고 / 대차잔고.
NOTE: do NOT attempt data.krx.co.kr login here (account is at 4/5 failed attempts)."""
import json
import requests

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")


def head(url, **kw):
    try:
        r = requests.get(url, headers={"User-Agent": UA}, timeout=20, **kw)
        return f"{r.status_code} len={len(r.text)} :: {r.text[:150]!r}"
    except Exception as e:
        return f"ERR {e!r}"


print("=== 1. KRX 공매도종합포털 ===")
for u in ["https://short.krx.co.kr/", "http://short.krx.co.kr/",
          "https://short.krx.co.kr/contents/SRT/01/01010100/SRT01010100.jsp"]:
    print(f"  {u}\n     {head(u)}")

print("\n=== 2. 네이버 금융 공매도 (종목별) ===")
print("  ", head("https://finance.naver.com/item/frgn.naver?code=005930"))

print("\n=== 3. KOFIA freesis (대차거래) ===")
try:
    r = requests.post(
        "https://freesis.kofia.or.kr/meta/getMetaDataList.do",
        headers={"User-Agent": UA, "Content-Type": "application/json;charset=UTF-8",
                 "Referer": "https://freesis.kofia.or.kr/"},
        data=json.dumps({"dmSearch": {"tmpV40": "", "tmpV41": "", "tmpV1": "",
                                      "tmpV12": "", "tmpV14": "", "tmpV45": "D",
                                      "tmpV5": "", "tmpV46": "1"}}),
        timeout=25)
    print("  ", r.status_code, r.text[:200])
except Exception as e:
    print("   ERR", repr(e))

print("\n=== 4. 세이브로 SEIBro 대차 ===")
print("  ", head("https://seibro.or.kr/websquare/control.jsp?w2xPath=/IPORTAL/user/loan/BIP_CNTS10011V.xml"))
