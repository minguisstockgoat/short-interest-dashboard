# -*- coding: utf-8 -*-
"""대시보드용 JSON 산출.

web/dashboard_data.json 구조
  meta   : 기준일·확정일·유니버스 정보
  stocks : 종목별 최신 스냅샷 (랭킹 테이블용)
  series : 종목별 시계열 (상세 차트용)

공매도/대차 원본이 아직 없으면 해당 필드를 비운 채로 생성한다.
"""
from __future__ import annotations

import argparse
import json

import numpy as np
import pandas as pd

from common import DASHBOARD_JSON, DATA, MIN_MKTCAP, log

UNIVERSE_CSV = DATA / "universe.csv"
PRICES_CSV = DATA / "prices.csv"
FLOAT_CSV = DATA / "free_float.csv"
PANEL_CSV = DATA / "short_panel.csv"
COEF_CSV = DATA / "short_coef.csv"
ESTIMATE_CSV = DATA / "short_estimate.csv"
ICE_CDS_CSV = DATA / "ice_cds.csv"

HIST_DAYS = 250


def _f(x):
    """JSON 안전 실수 변환."""
    if x is None:
        return None
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return None if not np.isfinite(v) else v


def _r(x, nd=3):
    v = _f(x)
    return None if v is None else round(v, nd)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--hist-days", type=int, default=HIST_DAYS)
    a = ap.parse_args()

    uni = pd.read_csv(UNIVERSE_CSV, dtype={"code": str})
    uni["code"] = uni["code"].str.zfill(6)
    codes = set(uni["code"])
    log(f"유니버스 {len(uni)}종목")

    prices = pd.read_csv(PRICES_CSV, dtype={"date": str, "code": str})
    prices["code"] = prices["code"].str.zfill(6)
    prices = prices[prices["code"].isin(codes)]
    all_dates = sorted(prices["date"].unique())
    hist_dates = all_dates[-a.hist_days:]
    prices = prices[prices["date"].isin(hist_dates)]
    asof = all_dates[-1]

    flt = pd.read_csv(FLOAT_CSV, dtype={"code": str})
    flt["code"] = flt["code"].str.zfill(6)

    # ---- 공매도/대차 (있으면) -------------------------------------------------
    panel = coef = est = None
    if PANEL_CSV.exists():
        panel = pd.read_csv(PANEL_CSV, dtype={"date": str, "code": str})
        panel["code"] = panel["code"].str.zfill(6)
        panel = panel[panel["code"].isin(codes) & panel["date"].isin(hist_dates)]
    if COEF_CSV.exists():
        coef = pd.read_csv(COEF_CSV, dtype={"code": str})
        coef["code"] = coef["code"].str.zfill(6)
    if ESTIMATE_CSV.exists():
        est = pd.read_csv(ESTIMATE_CSV, dtype={"code": str, "known_date": str,
                                               "asof": str})
        est["code"] = est["code"].str.zfill(6)

    has_short = panel is not None and not panel.empty
    log(f"공매도 패널: {'있음' if has_short else '없음 (시세/주식수만 산출)'}")

    # ---- 최신 시세 + 20일 평균거래량 -----------------------------------------
    last_px = prices.sort_values("date").groupby("code").tail(1).set_index("code")
    avg_vol = (prices.sort_values("date").groupby("code")["volume"]
               .apply(lambda s: s.tail(20).mean()).rename("avg_vol_20"))

    base = uni[["code", "name", "market", "list_shares"]].merge(
        flt[["code", "float_shares", "float_ratio"]], on="code", how="left")
    base = base.set_index("code")
    base["close"] = last_px["close"]
    base["mktcap"] = last_px["mktcap"]
    base["volume"] = last_px["volume"]
    base["avg_vol_20"] = avg_vol
    base["list_shares"] = last_px["list_shares"].fillna(base["list_shares"])

    # ---- 공매도 잔고 스냅샷 --------------------------------------------------
    known_date = None
    if has_short:
        bal = panel.dropna(subset=["bal_qty"])
        known_date = bal["date"].max()
        cur = bal[bal["date"] == known_date].set_index("code")["bal_qty"]
        base["bal_qty"] = cur

        bd = sorted(bal["date"].unique())

        def prev_bal(lag: int):
            if len(bd) <= lag:
                return None
            d = bd[-1 - lag]
            return bal[bal["date"] == d].set_index("code")["bal_qty"]

        for lag, label in ((1, "d1"), (5, "d5"), (20, "d20")):
            p = prev_bal(lag)
            base[f"chg_{label}"] = (base["bal_qty"] - p) if p is not None else np.nan

        base["short_vol"] = (panel[panel["date"] == asof]
                             .set_index("code")["short_vol"])
        base["loan_qty"] = (panel.dropna(subset=["loan_qty"])
                            .sort_values("date").groupby("code").tail(1)
                            .set_index("code")["loan_qty"])
    if coef is not None:
        c = coef.set_index("code")
        for col in ("alpha", "beta", "r2", "n_obs", "source"):
            if col in c:
                base[col] = c[col]
    if est is not None:
        e = est.set_index("code")
        base["bal_est"] = e["bal_est"]
        base["bal_known"] = e["bal_known"]

    # ---- 비율 계산 -----------------------------------------------------------
    ls, fs = base["list_shares"], base["float_shares"]
    if "bal_qty" in base:
        base["ratio_list"] = base["bal_qty"] / ls * 100
        base["ratio_float"] = base["bal_qty"] / fs * 100
        base["dtc"] = base["bal_qty"] / base["avg_vol_20"]
    if "bal_est" in base:
        base["est_ratio_list"] = base["bal_est"] / ls * 100
        base["est_ratio_float"] = base["bal_est"] / fs * 100

    base = base.reset_index()
    sort_col = "ratio_list" if "ratio_list" in base else "mktcap"
    base = base.sort_values(sort_col, ascending=False)

    stocks = []
    for r in base.to_dict("records"):
        stocks.append({
            "code": r["code"], "name": r["name"], "market": r["market"],
            "close": _f(r.get("close")), "mktcap": _f(r.get("mktcap")),
            "listShares": _f(r.get("list_shares")),
            "floatShares": _f(r.get("float_shares")),
            "floatRatio": _r(r.get("float_ratio"), 2),
            "avgVol20": _f(r.get("avg_vol_20")),
            "balQty": _f(r.get("bal_qty")),
            "ratioList": _r(r.get("ratio_list")),
            "ratioFloat": _r(r.get("ratio_float")),
            "chg1": _f(r.get("chg_d1")), "chg5": _f(r.get("chg_d5")),
            "chg20": _f(r.get("chg_d20")),
            "shortVol": _f(r.get("short_vol")), "loanQty": _f(r.get("loan_qty")),
            "dtc": _r(r.get("dtc"), 1),
            "balEst": _f(r.get("bal_est")),
            "estRatioList": _r(r.get("est_ratio_list")),
            "estRatioFloat": _r(r.get("est_ratio_float")),
            "alpha": _r(r.get("alpha"), 4), "beta": _r(r.get("beta"), 4),
            "r2": _r(r.get("r2"), 3), "nObs": _f(r.get("n_obs")),
            "coefSource": r.get("source") if isinstance(r.get("source"), str) else None,
        })

    # ---- 시계열 --------------------------------------------------------------
    series = {}
    px_by = {c: g for c, g in prices.sort_values("date").groupby("code")}
    pn_by = ({c: g for c, g in panel.sort_values("date").groupby("code")}
             if has_short else {})
    for code in base["code"]:
        g = px_by.get(code)
        if g is None or g.empty:
            continue
        rec = {"dates": g["date"].tolist(),
               "close": [_f(v) for v in g["close"]]}
        p = pn_by.get(code)
        if p is not None and not p.empty:
            merged = g[["date"]].merge(p, on="date", how="left")
            ls_v = _f(base.loc[base["code"] == code, "list_shares"].iloc[0])
            fs_v = _f(base.loc[base["code"] == code, "float_shares"].iloc[0])
            rec["balQty"] = [_f(v) for v in merged["bal_qty"]]
            rec["ratioList"] = [_r(v / ls_v * 100) if _f(v) is not None and ls_v else None
                                for v in merged["bal_qty"]]
            rec["ratioFloat"] = [_r(v / fs_v * 100) if _f(v) is not None and fs_v else None
                                 for v in merged["bal_qty"]]
            rec["shortVol"] = [_f(v) for v in merged["short_vol"]]
            rec["loanQty"] = [_f(v) for v in merged["loan_qty"]]
        series[code] = rec

    # ---- 신선도 -------------------------------------------------------------
    # 잔고는 T+2 공시라 거래일 2일치 지연은 정상이다. 그보다 더 벌어졌다면
    # 수집이 멈춘 것이므로 대시보드에 그대로 드러낸다(조용히 낡지 않게).
    short_lag = short_stale = None
    if known_date:
        short_lag = sum(1 for d in all_dates if d > known_date)
        short_stale = max(0, short_lag - 2)

    short_vol_asof = None
    if has_short and "short_vol" in panel:
        sv = panel.dropna(subset=["short_vol"])
        if not sv.empty:
            short_vol_asof = sv["date"].max()

    payload = {
        "meta": {
            "asof": asof, "knownDate": known_date,
            "universe": len(base), "minMktcap": MIN_MKTCAP,
            "hasShort": bool(has_short),
            "histDays": len(hist_dates),
            "shortLagDays": short_lag,        # 확정일이 기준일보다 며칠 뒤인지
            "shortStaleDays": short_stale,    # T+2 정상 지연을 뺀 초과 지연
            "shortVolAsof": short_vol_asof,
            "generatedAt": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M"),
        },
        "stocks": stocks,
        "series": series,
    }
    if ICE_CDS_CSV.exists():
        cds = pd.read_csv(ICE_CDS_CSV, dtype={"clearing_date": str, "ticker": str})
        cds = cds.sort_values(["ticker", "clearing_date"])
        items = []
        for ticker, group in cds.groupby("ticker"):
            row = group.iloc[-1]
            items.append({
                "entity": row["entity"], "ticker": ticker, "name": row["name"],
                "date": row["clearing_date"], "instrument": row["instrument_name"],
                "couponBp": _f(row["coupon_bp"]), "eodPrice": _r(row["eod_price"], 4),
                "prevPrice": _r(group.iloc[-2]["eod_price"], 4) if len(group) > 1 else None,
            })
        payload["cds"] = {
            "source": "ICE Clear Credit",
            "sourceUrl": "https://status.ice.com/cds-settlement-prices/icc/single-name-instruments",
            "note": "무료 공개 5년물 단일종목 CDS EOD 정산가격. 가격 하락은 신용위험 프리미엄 확대를 의미합니다.",
            "items": items,
        }

    DASHBOARD_JSON.write_text(json.dumps(payload, ensure_ascii=False,
                                         separators=(",", ":")), encoding="utf-8")
    mb = DASHBOARD_JSON.stat().st_size / 1e6
    log(f"저장: {DASHBOARD_JSON} ({mb:.1f} MB, {len(stocks)}종목, "
        f"시계열 {len(series)}종목 x {len(hist_dates)}일)")
    if short_stale:
        log(f"⚠ 공매도 잔고가 정상(T+2)보다 {short_stale}거래일 더 지연됨 "
            f"(확정 {known_date} / 기준 {asof})")


if __name__ == "__main__":
    main()
