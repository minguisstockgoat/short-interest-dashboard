# -*- coding: utf-8 -*-
"""KRX Data Marketplace OPEN API 수집기.

전종목 일별매매정보(KOSPI/KOSDAQ)를 받아 종가·거래량·시가총액·상장주식수를 적재한다.
휴장일은 빈 응답이므로 자동으로 걸러진다. 응답은 data/raw/open_api/ 에 캐시한다.
"""
from __future__ import annotations

import argparse
import datetime as dt
import gzip
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor

import pandas as pd
import requests

from common import DATA, MASTER_CSV, PRICES_CSV, RAW, log, parse_ymd, ymd

BASE = "https://data-dbg.krx.co.kr/svc/apis"
MARKETS = {"KOSPI": "sto/stk_bydd_trd", "KOSDAQ": "sto/ksq_bydd_trd"}
CACHE = RAW / "open_api"
CACHE.mkdir(parents=True, exist_ok=True)

KEEP = ["BAS_DD", "ISU_CD", "ISU_NM", "MKT_NM", "TDD_CLSPRC", "ACC_TRDVOL",
        "ACC_TRDVAL", "MKTCAP", "LIST_SHRS"]
NUM = ["TDD_CLSPRC", "ACC_TRDVOL", "ACC_TRDVAL", "MKTCAP", "LIST_SHRS"]


def _key() -> str:
    k = os.environ.get("KRX_API_KEY")
    if not k:
        raise SystemExit("KRX_API_KEY 환경변수가 없습니다.")
    return k


def fetch_day(market: str, day: dt.date, session: requests.Session,
              use_cache: bool = True) -> list[dict]:
    """하루치 한 시장 데이터를 가져온다. 휴장일이면 빈 리스트.

    ⚠ 빈 응답은 캐시하지 않는다. 아직 게시되기 전(장 마감 직후·이른 시각)에
    한 번 조회하면 빈 응답이 오는데, 이걸 캐시에 남기면 그 날짜는 영원히
    빈 값으로 고정된다 — 실제로 7/30~8/3 시세가 이렇게 통째로 유실됐다.
    휴장일이면 매번 한 번씩 더 물어보게 되지만, 그 비용이 훨씬 싸다.
    """
    path = CACHE / f"{market}_{ymd(day)}.json.gz"
    if use_cache and path.exists():
        try:
            with gzip.open(path, "rt", encoding="utf-8") as f:
                cached = json.load(f)
        except (OSError, ValueError):
            cached = None
        if cached:
            return cached
        path.unlink(missing_ok=True)      # 비어 있던 캐시는 버리고 다시 받는다

    url = f"{BASE}/{MARKETS[market]}"
    for attempt in range(4):
        try:
            r = session.get(url, params={"basDd": ymd(day)},
                            headers={"AUTH_KEY": _key()}, timeout=90)
            if r.status_code != 200:
                time.sleep(1.5 * (attempt + 1))
                continue
            rows = r.json().get("OutBlock_1") or []
            break
        except Exception:
            time.sleep(1.5 * (attempt + 1))
    else:
        log(f"  ! {market} {ymd(day)} 실패(재시도 초과)")
        return []

    slim = [{k: row.get(k, "") for k in KEEP} for row in rows]
    if slim:                              # 빈 응답은 남기지 않는다 (위 주석 참고)
        with gzip.open(path, "wt", encoding="utf-8") as f:
            json.dump(slim, f, ensure_ascii=False)
    return slim


def collect(start: dt.date, end: dt.date, workers: int = 6,
            use_cache: bool = True) -> pd.DataFrame:
    days = [d for d in pd.date_range(start, end, freq="D").date if d.weekday() < 5]
    jobs = [(m, d) for d in days for m in MARKETS]
    log(f"OPEN API 수집: {ymd(start)}~{ymd(end)} 영업일 후보 {len(days)}일 x {len(MARKETS)}시장 = {len(jobs)}건")

    out: list[dict] = []
    sess = requests.Session()
    done = 0
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = {ex.submit(fetch_day, m, d, sess, use_cache): (m, d) for m, d in jobs}
        for fut, (m, d) in futures.items():
            rows = fut.result()
            out.extend(rows)
            done += 1
            if done % 40 == 0:
                log(f"  진행 {done}/{len(jobs)} (누적 {len(out):,}행)")

    if not out:
        return pd.DataFrame(columns=KEEP)
    df = pd.DataFrame(out)
    for c in NUM:
        df[c] = pd.to_numeric(df[c].astype(str).str.replace(",", "", regex=False),
                              errors="coerce")
    df = df.rename(columns={
        "BAS_DD": "date", "ISU_CD": "code", "ISU_NM": "name", "MKT_NM": "market",
        "TDD_CLSPRC": "close", "ACC_TRDVOL": "volume", "ACC_TRDVAL": "value",
        "MKTCAP": "mktcap", "LIST_SHRS": "list_shares"})
    df = df.dropna(subset=["close"]).sort_values(["date", "code"])
    return df.reset_index(drop=True)


def merge_and_save(df_new: pd.DataFrame) -> pd.DataFrame:
    if PRICES_CSV.exists():
        old = pd.read_csv(PRICES_CSV, dtype={"date": str, "code": str})
        df = pd.concat([old, df_new], ignore_index=True)
    else:
        df = df_new
    df = df.drop_duplicates(subset=["date", "code"], keep="last")
    df = df.sort_values(["date", "code"]).reset_index(drop=True)
    df.to_csv(PRICES_CSV, index=False, encoding="utf-8-sig")

    last = df.sort_values("date").groupby("code").tail(1)
    master = last[["code", "name", "market", "list_shares", "close", "mktcap", "date"]]
    master = master.rename(columns={"date": "as_of"}).sort_values("code")
    master.to_csv(MASTER_CSV, index=False, encoding="utf-8-sig")
    log(f"저장: {PRICES_CSV.name} {len(df):,}행 / {MASTER_CSV.name} {len(master):,}종목")
    return df


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", required=True, help="YYYYMMDD")
    ap.add_argument("--end", required=True, help="YYYYMMDD")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--no-cache", action="store_true")
    a = ap.parse_args()
    df = collect(parse_ymd(a.start), parse_ymd(a.end), a.workers, not a.no_cache)
    if df.empty:
        log("수집 결과 없음")
        return
    merge_and_save(df)
    log(f"거래일 수: {df['date'].nunique()}일, 종목 수: {df['code'].nunique()}")


if __name__ == "__main__":
    main()
