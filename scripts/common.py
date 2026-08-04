# -*- coding: utf-8 -*-
"""공통 경로/유틸."""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
RAW = DATA / "raw"
WEB = ROOT / "docs"          # GitHub Pages는 / 또는 /docs 만 게시 가능
for _p in (DATA, RAW, WEB):
    _p.mkdir(parents=True, exist_ok=True)

# 어느 진입점(쉘 래퍼·launchd·수동 실행)에서든 .env 가 실리도록 여기서 한 번 읽는다
import envfile as _envfile  # noqa: E402
_envfile.load()

# 산출물 경로
PRICES_CSV = DATA / "prices.csv"          # 일별 시세 + 상장주식수 (전종목)
MASTER_CSV = DATA / "master.csv"          # 종목 마스터
FLOAT_CSV = DATA / "free_float.csv"       # 유동주식수 (FnGuide)
SHORT_BAL_CSV = DATA / "short_balance.csv"    # 공매도 잔고 (KRX, D-2까지)
SHORT_VOL_CSV = DATA / "short_volume.csv"     # 공매도 거래량 (KRX, D까지)
LOAN_BAL_CSV = DATA / "loan_balance.csv"      # 대차 잔고 (KRX)
DASHBOARD_JSON = WEB / "dashboard_data.json"


def ymd(d: dt.date) -> str:
    return d.strftime("%Y%m%d")


def parse_ymd(s: str) -> dt.date:
    return dt.datetime.strptime(str(s).strip(), "%Y%m%d").date()


def daterange(start: dt.date, end: dt.date):
    d = start
    while d <= end:
        yield d
        d += dt.timedelta(days=1)


def is_weekday(d: dt.date) -> bool:
    return d.weekday() < 5


def log(msg: str) -> None:
    print(f"[{dt.datetime.now():%H:%M:%S}] {msg}", flush=True)


# 대시보드 유니버스 기본값: 시가총액 1조원 이상
MIN_MKTCAP = 1_000_000_000_000


def load_universe(min_mktcap: int = MIN_MKTCAP):
    """master.csv에서 시총 기준을 만족하는 종목 마스터를 반환한다."""
    import pandas as pd

    if not MASTER_CSV.exists():
        raise SystemExit(f"{MASTER_CSV} 가 없습니다. 먼저 krx_open.py 를 실행하세요.")
    m = pd.read_csv(MASTER_CSV, dtype={"code": str})
    m["code"] = m["code"].astype(str).str.zfill(6)
    m["mktcap"] = pd.to_numeric(m["mktcap"], errors="coerce")
    m = m[m["mktcap"] >= min_mktcap].sort_values("mktcap", ascending=False)
    return m.reset_index(drop=True)
