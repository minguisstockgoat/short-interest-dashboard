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


# --------------------------------------------------------------- 담당 머신
# 이 대시보드는 맥·윈도우 두 대에 같은 저장소가 깔려 있어 양쪽이 번갈아 갱신·푸시해
# 왔다. 그 탓에 다른 PC 를 켤 때마다 KRX 로그인 요청이 뜨고 커밋도 중복된다.
# 그래서 '갱신을 담당하는 한 대'만 돌도록 막는다.
#
# 지정은 각 머신의 .env (git 미추적) 에 둔다 — 저장소가 공개라 호스트명을
# 커밋하지 않기 위해서다:
#     PRIMARY_HOST=<hostname>
# 값이 없거나 다른 머신이면 갱신 계열 스크립트는 아무것도 하지 않고 끝난다.
# 담당을 옮기려면 그 머신 .env 에 자기 hostname 을 적으면 된다.

def hostname() -> str:
    """비교용으로 정규화한 이 머신의 호스트명(도메인 제거·소문자)."""
    import socket
    return socket.gethostname().split(".")[0].strip().lower()


def is_primary() -> bool:
    import os
    want = os.environ.get("PRIMARY_HOST", "").split(".")[0].strip().lower()
    return bool(want) and want == hostname()


def require_primary(what: str) -> bool:
    """담당 머신이 아니면 사유를 찍고 False. 호출부는 조용히 끝내면 된다."""
    if is_primary():
        return True
    import os
    want = os.environ.get("PRIMARY_HOST", "").strip()
    log(f"{what}: 이 머신({hostname()})은 갱신 담당이 아니라 건너뜁니다."
        + (f" 담당={want}" if want else " (.env 에 PRIMARY_HOST 없음)"))
    return False


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


# 대시보드 유니버스 기본값: 시가총액 5,000억원 이상
# (2026-08-20 1조 → 5천억 확대. KRX 공매도·시세는 시장 단위 일괄 수집이라 요청 수가 늘지 않고,
#  종목별로 붙는 건 KOFIA 대차잔고와 FnGuide 유동주식수뿐이다.)
MIN_MKTCAP = 500_000_000_000


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
