# -*- coding: utf-8 -*-
"""종목기본정보(stk/ksq_isu_base_info)를 받아 master.csv에 종목 구분을 붙이고
개별 보통주만 남긴 유니버스(universe.csv)를 만든다.

제외 대상: 우선주, 스팩(SPAC), 리츠, 신주인수권, ETF/ETN(애초에 다른 API),
외국주권/뮤추얼펀드 등 SECUGRP_NM이 '주권'이 아닌 것.
"""
from __future__ import annotations

import argparse
import os

import pandas as pd
import requests

from common import DATA, MASTER_CSV, MIN_MKTCAP, log

BASE = "https://data-dbg.krx.co.kr/svc/apis"
INFO = {"KOSPI": "sto/stk_isu_base_info", "KOSDAQ": "sto/ksq_isu_base_info"}
UNIVERSE_CSV = DATA / "universe.csv"

# 스팩/리츠 등 사업회사가 아닌 종목 이름 패턴
NAME_EXCLUDE = ("스팩", "기업인수목적")


def fetch_info(bas_dd: str) -> pd.DataFrame:
    key = os.environ["KRX_API_KEY"]
    frames = []
    for mkt, path in INFO.items():
        r = requests.get(f"{BASE}/{path}", params={"basDd": bas_dd},
                         headers={"AUTH_KEY": key}, timeout=90)
        rows = r.json().get("OutBlock_1") or []
        log(f"  {mkt} 종목기본정보 {len(rows)}건")
        frames.append(pd.DataFrame(rows))
    df = pd.concat(frames, ignore_index=True)
    df["code"] = df["ISU_SRT_CD"].astype(str).str.zfill(6)
    return df[["code", "ISU_ABBRV", "MKT_TP_NM", "SECUGRP_NM", "SECT_TP_NM",
               "KIND_STKCERT_TP_NM", "LIST_DD"]].rename(columns={
        "ISU_ABBRV": "abbrv", "MKT_TP_NM": "market_info", "SECUGRP_NM": "secu_group",
        "SECT_TP_NM": "sector_tp", "KIND_STKCERT_TP_NM": "stock_kind",
        "LIST_DD": "list_date"})


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True, help="기준일 YYYYMMDD (최근 거래일)")
    ap.add_argument("--min-mktcap", type=float, default=MIN_MKTCAP)
    a = ap.parse_args()

    info = fetch_info(a.date)
    master = pd.read_csv(MASTER_CSV, dtype={"code": str})
    master["code"] = master["code"].astype(str).str.zfill(6)
    m = master.merge(info, on="code", how="left")

    m["is_common"] = (
        (m["secu_group"] == "주권")
        & (m["stock_kind"] == "보통주")
        & ~m["name"].astype(str).str.contains("|".join(NAME_EXCLUDE), na=False)
    )
    m.to_csv(MASTER_CSV, index=False, encoding="utf-8-sig")

    m["mktcap"] = pd.to_numeric(m["mktcap"], errors="coerce")
    uni = m[m["is_common"] & (m["mktcap"] >= a.min_mktcap)].copy()
    uni = uni.sort_values("mktcap", ascending=False).reset_index(drop=True)
    uni.to_csv(UNIVERSE_CSV, index=False, encoding="utf-8-sig")

    log(f"전체 {len(m):,}종목 → 보통주 {int(m['is_common'].sum()):,}종목 "
        f"→ 시총 {a.min_mktcap/1e12:.0f}조 이상 유니버스 {len(uni):,}종목")
    log(f"  KOSPI {int((uni['market'] == 'KOSPI').sum())} / "
        f"KOSDAQ {int((uni['market'] == 'KOSDAQ').sum())}")
    log(f"저장: {UNIVERSE_CSV}")
    print(uni[["code", "name", "market", "mktcap", "list_shares"]].head(10).to_string(index=False))


if __name__ == "__main__":
    main()
