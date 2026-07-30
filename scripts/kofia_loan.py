# -*- coding: utf-8 -*-
"""금융투자협회 FreeSIS에서 종목별 대차거래 잔고를 수집한다.

엔드포인트 (로그인 불필요, 순수 JSON)
  POST https://freesis.kofia.or.kr/meta/getMetaDataList.do
  {"dmSearch":{"tmpV1":"D","tmpV45":"<시작YYYYMMDD>","tmpV46":"<종료>",
               "tmpV72":"<종목코드6자리>","OBJ_NM":"STATSCU0100000140BO"}}

응답 ds1 컬럼
  TMPV1 일자 / TMPV2 종목명 / TMPV3 대차체결(주) / TMPV4 대차상환(주)
  TMPV5 대차잔고(주) / TMPV6 대차잔고금액(백만원)

종목당 1회 요청으로 기간 전체를 받는다. KRX와 달리 D일까지 제공된다.
"""
from __future__ import annotations

import argparse
import datetime as dt
import gzip
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
import requests

from common import DATA, LOAN_BAL_CSV, RAW, log

BASE = "https://freesis.kofia.or.kr"
URL = f"{BASE}/meta/getMetaDataList.do"
HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"),
    "Content-Type": "application/json;charset=UTF-8",
    "Referer": f"{BASE}/stat/FreeSIS.do",
    "Accept": "application/json, text/plain, */*",
}
CACHE = RAW / "kofia_loan"
CACHE.mkdir(parents=True, exist_ok=True)
UNIVERSE_CSV = DATA / "universe.csv"

COLS = {"TMPV1": "date", "TMPV2": "name", "TMPV3": "loan_new",
        "TMPV4": "loan_ret", "TMPV5": "loan_qty", "TMPV6": "loan_amt_mn"}

# 협회 서버에도 예의를 지킨다 (KRX 차단 경험 반영)
_LOCK = threading.Lock()
_LAST = [0.0]
MIN_INTERVAL = 0.35


def _throttle() -> None:
    with _LOCK:
        wait = MIN_INTERVAL - (time.time() - _LAST[0])
        if wait > 0:
            time.sleep(wait)
        _LAST[0] = time.time()


def fetch_one(session, code: str, start: str, end: str, use_cache: bool = True):
    path = CACHE / f"{code}_{start}_{end}.json.gz"
    if use_cache and path.exists():
        try:
            with gzip.open(path, "rt", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            path.unlink(missing_ok=True)

    payload = {"dmSearch": {"tmpV40": "1000000", "tmpV41": "1", "tmpV1": "D",
                            "tmpV45": start, "tmpV46": end, "tmpV72": code,
                            "OBJ_NM": "STATSCU0100000140BO"}}
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    for attempt in range(3):
        try:
            _throttle()
            r = session.post(URL, data=body, timeout=40)
            if r.status_code == 403:
                raise SystemExit("\n[중단] FreeSIS가 403을 반환했습니다 — 잠시 후 재시도하세요.")
            if not r.text.strip().startswith("{"):
                time.sleep(1.0 * (attempt + 1))
                continue
            rows = r.json().get("ds1") or []
            with gzip.open(path, "wt", encoding="utf-8") as f:
                json.dump(rows, f, ensure_ascii=False)
            return rows
        except SystemExit:
            raise
        except Exception:
            time.sleep(1.0 * (attempt + 1))
    return []


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", required=True, help="YYYYMMDD")
    ap.add_argument("--end", required=True, help="YYYYMMDD")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--no-cache", action="store_true")
    a = ap.parse_args()

    uni = pd.read_csv(UNIVERSE_CSV, dtype={"code": str})
    codes = uni["code"].astype(str).str.zfill(6).tolist()
    log(f"대차잔고 수집: {len(codes)}종목 x 1요청 ({a.start} ~ {a.end})")

    session = requests.Session()
    session.headers.update(HEADERS)

    out, done, empty = [], 0, []
    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        futs = {ex.submit(fetch_one, session, c, a.start, a.end, not a.no_cache): c
                for c in codes}
        for f in as_completed(futs):
            code = futs[f]
            rows = f.result()
            if not rows:
                empty.append(code)
            for row in rows:
                rec = {"code": code}
                for src, dst in COLS.items():
                    rec[dst] = row.get(src)
                out.append(rec)
            done += 1
            if done % 50 == 0:
                log(f"  진행 {done}/{len(codes)} (누적 {len(out):,}행)")

    if not out:
        log("수집 결과 없음")
        return

    df = pd.DataFrame(out)
    df["date"] = df["date"].astype(str).str.replace("-", "", regex=False).str.strip()
    for c in ("loan_new", "loan_ret", "loan_qty", "loan_amt_mn"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df[["date", "code", "loan_qty", "loan_new", "loan_ret", "loan_amt_mn"]]
    # 응답 말미에 '합계' 요약 행이 섞여 있다 — 실제 일자 8자리만 남긴다.
    df = df[df["date"].str.fullmatch(r"\d{8}", na=False)]
    df = (df.dropna(subset=["date"])
            .drop_duplicates(subset=["date", "code"], keep="last")
            .sort_values(["date", "code"]).reset_index(drop=True))

    if LOAN_BAL_CSV.exists():
        old = pd.read_csv(LOAN_BAL_CSV, dtype={"date": str, "code": str})
        old["code"] = old["code"].astype(str).str.zfill(6)
        df = (pd.concat([old, df], ignore_index=True)
                .drop_duplicates(subset=["date", "code"], keep="last")
                .sort_values(["date", "code"]).reset_index(drop=True))
    df.to_csv(LOAN_BAL_CSV, index=False, encoding="utf-8-sig")
    log(f"저장 {LOAN_BAL_CSV.name}: {len(df):,}행 "
        f"({df['date'].nunique()}일 {df['date'].min()}~{df['date'].max()}, "
        f"{df['code'].nunique()}종목)")
    if empty:
        log(f"  미수집 {len(empty)}종목: {empty[:15]}")


if __name__ == "__main__":
    main()
