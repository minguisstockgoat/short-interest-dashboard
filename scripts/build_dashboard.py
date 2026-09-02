# -*- coding: utf-8 -*-
"""대시보드용 JSON 산출.

두 파일로 나눠 쓴다. 표를 그리는 데 필요한 건 stocks(0.2MB)뿐인데 시계열이
6MB라, 한 파일이면 첫 화면이 전부 받을 때까지 아무것도 안 나온다.

web/dashboard_data.json  — 첫 화면용 (작다)
  meta   : 기준일·확정일·유니버스 정보
  stocks : 종목별 최신 스냅샷 (랭킹 테이블용)
  spark  : 표 안 스파크라인용 최근 60거래일 잔고비율만

web/series.json          — 상세 차트용 (크다, 화면 그린 뒤 뒤따라 받는다)
  dates  : 공통 날짜 배열 한 벌
  s      : 종목별 시계열. dates 는 담지 않는다 — 모든 종목이 공통 배열의
           뒷부분이라(신규상장은 짧다) 값 배열 길이로 잘라 쓴다.

공매도/대차 원본이 아직 없으면 해당 필드를 비운 채로 생성한다.
"""
from __future__ import annotations

import argparse
import json

import numpy as np
import pandas as pd

from common import DASHBOARD_JSON, DATA, MIN_MKTCAP, log

SERIES_JSON = DASHBOARD_JSON.with_name("series.json")

UNIVERSE_CSV = DATA / "universe.csv"
PRICES_CSV = DATA / "prices.csv"
FLOAT_CSV = DATA / "free_float.csv"
PANEL_CSV = DATA / "short_panel.csv"
COEF_CSV = DATA / "short_coef.csv"
ESTIMATE_CSV = DATA / "short_estimate.csv"
EST_PATH_CSV = DATA / "short_estimate_path.csv"
ICE_CDS_CSV = DATA / "ice_cds.csv"

HIST_DAYS = 250
SPARK_DAYS = 60     # 표 안 스파크라인이 보여주는 구간


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

    est_path = None
    if EST_PATH_CSV.exists():
        est_path = pd.read_csv(EST_PATH_CSV, dtype={"date": str, "code": str})
        if not est_path.empty:
            est_path["code"] = est_path["code"].str.zfill(6)
            est_path = est_path[est_path["code"].isin(codes)
                                & est_path["date"].isin(hist_dates)]

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
    ep_by = ({c: dict(zip(g["date"], g["bal_est"]))
              for c, g in est_path.groupby("code")}
             if est_path is not None and not est_path.empty else {})
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

            # 미공시 구간 추정선. 확정선의 마지막 점을 시작점으로 함께 담아
            # 두 선이 끊기지 않고 이어지게 한다.
            # 250일 중 3일만 값이 있어 전체 길이 배열로 두면 null 이 1MB 넘게
            # 붙는다. 시작 인덱스와 구간만 담고 화면에서 펼친다.
            ep = ep_by.get(code)
            if ep:
                ev = [_f(ep.get(d)) for d in merged["date"]]
                bq = list(merged["bal_qty"])
                anchor = max((i for i, v in enumerate(bq) if _f(v) is not None),
                             default=None)
                if anchor is not None and ev[anchor] is None:
                    ev[anchor] = _f(bq[anchor])
                start = next((i for i, v in enumerate(ev) if v is not None), None)
                if start is not None:
                    seg = ev[start:]
                    rec["est"] = {
                        "i": start,
                        "balEst": seg,
                        "ratioList": [_r(v / ls_v * 100) if v is not None and ls_v
                                      else None for v in seg],
                        "ratioFloat": [_r(v / fs_v * 100) if v is not None and fs_v
                                       else None for v in seg],
                    }
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

    # ---- 출력 분리 -----------------------------------------------------------
    def _trim(rec):
        """표 안 스파크라인용으로 최근 SPARK_DAYS 만 남긴다. 높이 22px 짜리
        선이라 소수 2자리면 남는다."""
        rl = rec.get("ratioList")
        if not rl:
            return None
        cut = max(0, len(rl) - SPARK_DAYS)
        out = {"ratioList": [_r(v, 2) for v in rl[cut:]],
               "ratioFloat": [_r(v, 2) for v in rec.get("ratioFloat", [])[cut:]]}
        e = rec.get("est")
        if e:
            out["est"] = {"i": max(0, e["i"] - cut),
                          "ratioList": [_r(v, 2) for v in e["ratioList"]],
                          "ratioFloat": [_r(v, 2) for v in e["ratioFloat"]]}
        return out

    spark = {}
    for c, r in series.items():
        t = _trim(r)
        if t:
            spark[c] = t

    # 시계열의 dates 는 종목마다 담으면 그것만 1.2MB다. 모두 공통 배열의
    # 뒷부분이므로(신규상장은 짧게 시작한다) 한 벌만 담고 화면에서 값 배열
    # 길이로 잘라 쓴다. 혹시 뒷부분이 아닌 종목이 나오면 그 종목만 자기
    # dates 를 들고 가게 해서 조용히 어긋나지 않게 한다.
    shared_dates = max((r["dates"] for r in series.values()), key=len, default=[])
    series_out, own = {}, 0
    for c, r in series.items():
        rec = {k: v for k, v in r.items() if k != "dates"}
        n = len(r["dates"])
        if n and r["dates"] != shared_dates[-n:]:
            rec["dates"] = r["dates"]
            own += 1
        series_out[c] = rec
    if own:
        log(f"공통 날짜와 어긋나 자체 dates 를 담은 종목: {own}")

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
        "spark": spark,
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

    _dump = lambda path, obj: path.write_text(
        json.dumps(obj, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    _dump(DASHBOARD_JSON, payload)
    _dump(SERIES_JSON, {"dates": shared_dates, "s": series_out})
    mb = DASHBOARD_JSON.stat().st_size / 1e6
    smb = SERIES_JSON.stat().st_size / 1e6
    log(f"저장: {DASHBOARD_JSON.name} ({mb:.2f} MB, 첫 화면용 {len(stocks)}종목) + "
        f"{SERIES_JSON.name} ({smb:.2f} MB, 시계열 {len(series)}종목 x {len(hist_dates)}일)")
    if short_stale:
        log(f"⚠ 공매도 잔고가 정상(T+2)보다 {short_stale}거래일 더 지연됨 "
            f"(확정 {known_date} / 기준 {asof})")


if __name__ == "__main__":
    main()
