# -*- coding: utf-8 -*-
"""KRX 정보데이터시스템 공매도 데이터 수집 (로그인 세션 필요).

확정된 화면
  short_balance : 개별종목 공매도 순보유잔고  MDCSTAT30501 (searchType=1, mktTpCd=1|2)
                  → ISU_CD, ISU_ABBRV, BAL_QTY, LIST_SHRS, BAL_AMT, MKTCAP, BAL_RTO
                  잔고는 T+2 공시라 최근 1~2거래일은 비어 있는 것이 정상이다.
  short_volume  : 개별종목 공매도 거래        MDCSTAT30101 (searchType=1, mktId=STK|KSQ)
                  → ISU_CD, CVSRTSELL_TRDVOL(공매도 거래량), ACC_TRDVOL, TRDVOL_WT
  loan_balance  : 대차거래 잔고 (bld 확정 시 LOAN_BLD 채움)

세션은 krx_session.build_session() 이 크롬(원격 디버깅 9222)에서 빌려온다.
"""
from __future__ import annotations

import argparse
import gzip
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd

from common import (DATA, LOAN_BAL_CSV, RAW, SHORT_BAL_CSV, SHORT_VOL_CSV, log)
from krx_session import JSON_URL, ensure_session

CACHE = RAW / "krx_short"
CACHE.mkdir(parents=True, exist_ok=True)

COMMON = {"locale": "ko_KR", "share": "1", "money": "1", "csvxls_isNo": "false"}

# KRX는 짧은 시간에 요청이 몰리면 엣지단에서 IP를 차단한다(전 도메인 403).
# 한 번 막히면 몇 시간 단위로 풀리지 않으므로 전역 레이트리밋을 건다.
_RATE_LOCK = __import__("threading").Lock()
_LAST_CALL = [0.0]
MIN_INTERVAL = 0.7   # 초, 전체 워커 합산 기준


def _throttle() -> None:
    with _RATE_LOCK:
        wait = MIN_INTERVAL - (time.time() - _LAST_CALL[0])
        if wait > 0:
            time.sleep(wait)
        _LAST_CALL[0] = time.time()

SPECS = {
    "short_balance": {
        "bld": "dbms/MDC/STAT/srt/MDCSTAT30501",
        "mkt": {"KOSPI": {"mktTpCd": "1"}, "KOSDAQ": {"mktTpCd": "2"}},
        "extra": {"searchType": "1"},
        "cols": {"ISU_CD": "code", "BAL_QTY": "bal_qty", "BAL_AMT": "bal_amt",
                 "BAL_RTO": "bal_rto", "LIST_SHRS": "list_shrs"},
        "dest": SHORT_BAL_CSV,
    },
    "short_volume": {
        "bld": "dbms/MDC/STAT/srt/MDCSTAT30101",
        "mkt": {"KOSPI": {"mktId": "STK"}, "KOSDAQ": {"mktId": "KSQ"}},
        "extra": {"searchType": "1", "secugrpId": "STMFRTSCIFDRFS",
                  "inqCond": "STMFRTSCIFDRFSSRSWBC"},
        "cols": {"ISU_CD": "code", "CVSRTSELL_TRDVOL": "short_vol",
                 "ACC_TRDVOL": "acc_trdvol", "TRDVOL_WT": "short_wt"},
        "dest": SHORT_VOL_CSV,
    },
}

# 대차거래 잔고: bld 확정 후 아래를 채우면 동일 파이프라인으로 수집된다.
LOAN_SPEC = None


def _num(s):
    if s is None:
        return None
    s = str(s).replace(",", "").strip()
    if s in ("", "-", "N/A"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def fetch(session, kind: str, market: str, day: str, use_cache: bool = True):
    spec = SPECS[kind] if kind in SPECS else LOAN_SPEC
    path = CACHE / f"{kind}_{market}_{day}.json.gz"
    if use_cache and path.exists():
        try:
            with gzip.open(path, "rt", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            path.unlink(missing_ok=True)

    p = {**COMMON, **spec["extra"], **spec["mkt"][market], "bld": spec["bld"],
         "trdDd": day, "strtDd": day, "endDd": day}
    for attempt in range(3):
        try:
            _throttle()
            r = session.post(JSON_URL, data=p, timeout=60)
            if r.status_code == 403:
                raise SystemExit(
                    "\n[중단] KRX가 403(Access Denied)을 반환했습니다 — IP 차단입니다.\n"
                    "  더 요청하면 차단이 길어집니다. 수 시간 후 재시도하세요.\n"
                    "  이미 받은 분량은 `py scripts/krx_short.py --from-cache` 로 복원됩니다.")
            if not r.text.strip().startswith("{"):
                time.sleep(1.0 * (attempt + 1))
                continue
            rows = r.json().get("OutBlock_1") or []
            with gzip.open(path, "wt", encoding="utf-8") as f:
                json.dump(rows, f, ensure_ascii=False)
            return rows
        except Exception:
            time.sleep(1.0 * (attempt + 1))
    log(f"  ! {kind} {market} {day} 실패")
    return []


def collect(session, kind: str, days: list[str], workers: int, use_cache: bool):
    spec = SPECS[kind] if kind in SPECS else LOAN_SPEC
    jobs = [(m, d) for d in days for m in spec["mkt"]]
    log(f"[{kind}] {len(days)}거래일 x {len(spec['mkt'])}시장 = {len(jobs)}건")
    out, done, empty = [], 0, 0
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(fetch, session, kind, m, d, use_cache): (m, d)
                for m, d in jobs}
        for f in as_completed(futs):
            m, d = futs[f]
            rows = f.result()
            if not rows:
                empty += 1
            for row in rows:
                rec = {"date": d, "market": m}
                for src, dst in spec["cols"].items():
                    v = row.get(src)
                    rec[dst] = str(v).strip() if dst == "code" else _num(v)
                out.append(rec)
            done += 1
            if done % 100 == 0:
                log(f"  진행 {done}/{len(jobs)} (누적 {len(out):,}행)")

    if not out:
        log(f"[{kind}] 수집 결과 없음")
        return pd.DataFrame()
    df = pd.DataFrame(out)
    df["code"] = df["code"].astype(str).str.zfill(6)
    df = df.drop_duplicates(subset=["date", "code"], keep="last")
    df = df.sort_values(["date", "code"]).reset_index(drop=True)

    dest = spec["dest"]
    if dest.exists():
        old = pd.read_csv(dest, dtype={"date": str, "code": str})
        old["code"] = old["code"].astype(str).str.zfill(6)
        df = (pd.concat([old, df], ignore_index=True)
                .drop_duplicates(subset=["date", "code"], keep="last")
                .sort_values(["date", "code"]).reset_index(drop=True))
    df.to_csv(dest, index=False, encoding="utf-8-sig")
    log(f"[{kind}] 저장 {dest.name}: {len(df):,}행 "
        f"({df['date'].nunique()}일, {df['code'].nunique()}종목, 빈응답 {empty}건)")
    return df


def rebuild_from_cache(kind: str) -> pd.DataFrame:
    """네트워크 없이 data/raw/krx_short 캐시만으로 CSV를 재구성한다.

    KRX가 IP 차단 중이거나 오프라인일 때 사용한다.
    """
    spec = SPECS[kind] if kind in SPECS else LOAN_SPEC
    files = sorted(CACHE.glob(f"{kind}_*.json.gz"))
    log(f"[{kind}] 캐시 {len(files)}개 파일에서 복원")
    out = []
    for path in files:
        stem = path.name[:-len(".json.gz")]
        parts = stem.split("_")
        market, day = parts[-2], parts[-1]
        try:
            with gzip.open(path, "rt", encoding="utf-8") as f:
                rows = json.load(f)
        except Exception:
            continue
        for row in rows:
            rec = {"date": day, "market": market}
            for src, dst in spec["cols"].items():
                v = row.get(src)
                rec[dst] = str(v).strip() if dst == "code" else _num(v)
            out.append(rec)

    if not out:
        log(f"[{kind}] 캐시 없음")
        return pd.DataFrame()
    df = pd.DataFrame(out)
    df["code"] = df["code"].astype(str).str.zfill(6)
    df = (df.drop_duplicates(subset=["date", "code"], keep="last")
            .sort_values(["date", "code"]).reset_index(drop=True))
    dest = spec["dest"]
    df.to_csv(dest, index=False, encoding="utf-8-sig")
    log(f"[{kind}] 저장 {dest.name}: {len(df):,}행 "
        f"({df['date'].nunique()}일 {df['date'].min()}~{df['date'].max()}, "
        f"{df['code'].nunique()}종목)")
    return df


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start")
    ap.add_argument("--end")
    ap.add_argument("--from-cache", action="store_true",
                    help="네트워크 없이 캐시만으로 CSV 재구성")
    ap.add_argument("--kinds", default="short_balance,short_volume")
    ap.add_argument("--workers", type=int, default=2,
                    help="동시 요청 수 (KRX 차단 방지를 위해 낮게 유지)")
    ap.add_argument("--no-cache", action="store_true")
    a = ap.parse_args()

    if a.from_cache:
        for kind in a.kinds.split(","):
            kind = kind.strip()
            if kind in SPECS or (kind == "loan_balance" and LOAN_SPEC):
                rebuild_from_cache(kind)
        return

    if not (a.start and a.end):
        raise SystemExit("--start/--end 또는 --from-cache 가 필요합니다.")

    session = ensure_session()
    # 거래일 후보: 시세 + 대차잔고의 합집합.
    # KRX 공매도 화면은 시세 OPEN API보다 하루 빠를 때가 있어 시세만 보면 최신일을 놓친다.
    cal: set[str] = set()
    prices = pd.read_csv(DATA / "prices.csv", dtype={"date": str}, usecols=["date"])
    cal |= set(prices["date"].unique())
    if LOAN_BAL_CSV.exists():
        loan = pd.read_csv(LOAN_BAL_CSV, dtype={"date": str}, usecols=["date"])
        cal |= set(loan["date"].unique())
    days = sorted(d for d in cal if a.start <= d <= a.end)
    log(f"거래일 {len(days)}일 ({days[0]} ~ {days[-1]})")

    for kind in a.kinds.split(","):
        kind = kind.strip()
        if kind not in SPECS and not (kind == "loan_balance" and LOAN_SPEC):
            log(f"[{kind}] bld 미확정 — 건너뜀")
            continue
        collect(session, kind, days, a.workers, not a.no_cache)


if __name__ == "__main__":
    main()
