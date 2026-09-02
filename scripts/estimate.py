# -*- coding: utf-8 -*-
"""D일 추정 공매도잔고 및 종목별 α·β 회귀 추정.

모델
----
공매도잔고는 T+2 시차로 공시되므로 D일 시점에 확정치는 D-2까지만 알 수 있다.
잔고 증감을 두 관측 가능한 동인으로 설명한다.

    ΔBal(t) = α · ΔLoan(t) + β · ShortVol(t) + ε(t)

  ΔBal(t)     : 공매도잔고 증감 (주)  = Bal(t) - Bal(t-1)
  ΔLoan(t)    : 대차잔고 증감 (주)
  ShortVol(t) : 당일 공매도 거래량 (주)

α·β는 종목별로 최근 WINDOW(기본 60, 최소 20) 거래일 실제 잔고 증감에 대해
절편 없는 OLS로 매일 재추정한다. 세 변수 모두 '주식 수' 단위라 단위 정합적이다.

D일 추정
--------
D-2 확정잔고에서 미공시 2거래일(D-1, D)의 증감을 모델로 채운다.

    Est(D) = Bal(D-2) + Σ_{t∈{D-1, D}} [ α·ΔLoan(t) + β·ShortVol(t) ]

표본 부족·특이행렬·설명력 부족(R² < min_r2) 종목은 유니버스 풀링 회귀로
추정한 α·β를 폴백으로 사용한다. 경제적 의미상 α, β는 0~1 구간이 자연스러워
최종 추정에는 클리핑한 값을 쓰고, 원값도 함께 저장한다.
"""
from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

from common import (DATA, LOAN_BAL_CSV, SHORT_BAL_CSV, SHORT_VOL_CSV, log)

COEF_CSV = DATA / "short_coef.csv"
ESTIMATE_CSV = DATA / "short_estimate.csv"
EST_PATH_CSV = DATA / "short_estimate_path.csv"
PANEL_CSV = DATA / "short_panel.csv"

ALPHA_CLIP = (0.0, 1.0)
BETA_CLIP = (0.0, 1.0)


# --------------------------------------------------------------------- 패널 구성
def build_panel() -> pd.DataFrame:
    """공매도잔고 · 공매도거래량 · 대차잔고를 (date, code) 패널로 결합한다.

    대차잔고(loan_balance.csv)는 선택 사항이다. 없으면 ΔLoan=0으로 두고
    β(공매도 거래량) 항만으로 회귀·추정한다.
    """
    for req in (SHORT_BAL_CSV, SHORT_VOL_CSV):
        if not req.exists():
            raise SystemExit(f"필수 원본이 없습니다: {req.name}")

    bal = pd.read_csv(SHORT_BAL_CSV, dtype={"date": str, "code": str})
    vol = pd.read_csv(SHORT_VOL_CSV, dtype={"date": str, "code": str})
    bal["code"] = bal["code"].astype(str).str.zfill(6)
    vol["code"] = vol["code"].astype(str).str.zfill(6)

    keep_bal = ["date", "code", "bal_qty"]
    keep_vol = ["date", "code", "short_vol", "acc_trdvol"]
    p = (bal[[c for c in keep_bal if c in bal]]
         .merge(vol[[c for c in keep_vol if c in vol]],
                on=["date", "code"], how="outer"))

    if LOAN_BAL_CSV.exists():
        loan = pd.read_csv(LOAN_BAL_CSV, dtype={"date": str, "code": str})
        loan["code"] = loan["code"].astype(str).str.zfill(6)
        p = p.merge(loan[["date", "code", "loan_qty"]],
                    on=["date", "code"], how="outer")
        log("대차잔고 결합: 있음 (α 추정)")
    else:
        p["loan_qty"] = np.nan
        log("대차잔고 결합: 없음 → ΔLoan=0, β만 추정")

    p = p.sort_values(["code", "date"]).reset_index(drop=True)
    g = p.groupby("code", sort=False)
    p["d_bal"] = g["bal_qty"].diff()
    p["d_loan"] = g["loan_qty"].diff().fillna(0.0)
    # short_vol 은 미관측(NaN)과 실제 0을 구분해야 한다. 0으로 채우면
    # 미수집 구간이 "공매도 없음"으로 둔갑해 β가 0쪽으로 끌려간다.
    p["has_vol"] = p["short_vol"].notna()
    p.to_csv(PANEL_CSV, index=False, encoding="utf-8-sig")
    log(f"패널 저장: {PANEL_CSV.name} {len(p):,}행 "
        f"({p['code'].nunique()}종목, {p['date'].nunique()}일)")
    return p


# ------------------------------------------------------------------------ 회귀
def _ols_no_intercept(X: np.ndarray, y: np.ndarray) -> tuple[np.ndarray, float]:
    """절편 없는 OLS. 계수와 R²(중심화하지 않은 정의)를 반환."""
    coef, *_ = np.linalg.lstsq(X, y, rcond=None)
    resid = y - X @ coef
    ss_res = float(resid @ resid)
    ss_tot = float(y @ y)
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else np.nan
    return coef, r2


def fit_one(df: pd.DataFrame, window: int, min_obs: int):
    """한 종목의 최근 window 거래일로 α·β를 추정."""
    d = df[df["has_vol"]].dropna(subset=["d_bal", "d_loan", "short_vol"]).tail(window)
    n = len(d)
    if n < min_obs:
        return None
    X = d[["d_loan", "short_vol"]].to_numpy(dtype=float)
    y = d["d_bal"].to_numpy(dtype=float)
    if not np.isfinite(X).all() or not np.isfinite(y).all():
        return None
    # 설명변수가 사실상 상수(0)면 추정 불가
    if np.allclose(X.std(axis=0), 0):
        return None
    try:
        coef, r2 = _ols_no_intercept(X, y)
    except np.linalg.LinAlgError:
        return None
    if not np.isfinite(coef).all():
        return None
    return {"n_obs": n, "alpha_raw": float(coef[0]), "beta_raw": float(coef[1]),
            "r2": float(r2)}


def fit_all(panel: pd.DataFrame, window: int, min_obs: int, min_r2: float) -> pd.DataFrame:
    """종목별 회귀 + 풀링 폴백."""
    pooled_src = panel[panel["has_vol"]].dropna(
        subset=["d_bal", "d_loan", "short_vol"])
    last_dates = sorted(panel["date"].unique())[-window:]
    pooled_src = pooled_src[pooled_src["date"].isin(last_dates)]
    pX = pooled_src[["d_loan", "short_vol"]].to_numpy(dtype=float)
    py = pooled_src["d_bal"].to_numpy(dtype=float)
    pooled_coef, pooled_r2 = _ols_no_intercept(pX, py)
    log(f"풀링 회귀: n={len(pooled_src):,}  α={pooled_coef[0]:.4f}  "
        f"β={pooled_coef[1]:.4f}  R²={pooled_r2:.3f}")

    rows = []
    for code, g in panel.groupby("code", sort=False):
        fit = fit_one(g, window, min_obs)
        if fit is None or not np.isfinite(fit["r2"]) or fit["r2"] < min_r2:
            rows.append({
                "code": code,
                "alpha_raw": pooled_coef[0], "beta_raw": pooled_coef[1],
                "r2": fit["r2"] if fit else np.nan,
                "n_obs": fit["n_obs"] if fit else 0,
                "source": "pooled"})
        else:
            rows.append({"code": code, **fit, "source": "stock"})

    c = pd.DataFrame(rows)
    c["alpha"] = c["alpha_raw"].clip(*ALPHA_CLIP)
    c["beta"] = c["beta_raw"].clip(*BETA_CLIP)
    c["clipped"] = (c["alpha"] != c["alpha_raw"]) | (c["beta"] != c["beta_raw"])
    c.to_csv(COEF_CSV, index=False, encoding="utf-8-sig")
    log(f"계수 저장: {COEF_CSV.name} {len(c)}종목 "
        f"(종목별 {int((c['source'] == 'stock').sum())} / 풀링폴백 "
        f"{int((c['source'] == 'pooled').sum())})")
    return c


# ------------------------------------------------------------------------ 추정
def estimate(panel: pd.DataFrame, coef: pd.DataFrame, asof: str | None = None) -> pd.DataFrame:
    """D-2 확정잔고 + 미공시 구간(D-1, D) 모델 증감 = D일 추정잔고."""
    dates = sorted(panel["date"].unique())
    asof = asof or dates[-1]
    if asof not in dates:
        raise SystemExit(f"{asof} 는 패널에 없는 날짜입니다.")
    i = dates.index(asof)

    # 확정 잔고가 존재하는 마지막 날짜(보통 D-2)
    known = panel.dropna(subset=["bal_qty"])
    last_known = known["date"].max()
    gap_dates = [d for d in dates if last_known < d <= asof]

    cm = coef.set_index("code")[["alpha", "beta", "source", "r2", "n_obs"]]
    base = (known[known["date"] == last_known]
            .set_index("code")[["bal_qty"]].rename(columns={"bal_qty": "bal_known"}))

    gap = panel[panel["date"].isin(gap_dates)].copy()
    gap = gap.join(cm, on="code")
    gap["delta_hat"] = (gap["alpha"].fillna(0) * gap["d_loan"].fillna(0)
                        + gap["beta"].fillna(0) * gap["short_vol"].fillna(0))
    inc = gap.groupby("code")["delta_hat"].sum().rename("delta_hat_sum")

    # 미공시 구간의 '일자별' 추정 경로. D일 스칼라만 있으면 대시보드가 D-1을
    # 그릴 수 없어 잔고 선이 확정일에서 끊긴다. D-2 확정값에서 하루씩 누적한
    # 값을 따로 떨궈 차트가 확정 구간에 이어붙일 수 있게 한다.
    # 마지막 날 값은 정의상 out["bal_est"] 와 정확히 일치한다.
    if gap.empty:
        path = pd.DataFrame(columns=["date", "code", "bal_est"])
    else:
        path = gap.sort_values(["code", "date"]).copy()
        path["cum"] = path.groupby("code")["delta_hat"].cumsum()
        path = path.join(base, on="code").dropna(subset=["bal_known"])
        path["bal_est"] = (path["bal_known"] + path["cum"]).clip(lower=0)
        path = path[["date", "code", "bal_est"]]
    path.to_csv(EST_PATH_CSV, index=False, encoding="utf-8-sig")

    out = base.join(inc, how="left").join(cm, how="left")
    out["delta_hat_sum"] = out["delta_hat_sum"].fillna(0.0)
    out["bal_est"] = out["bal_known"] + out["delta_hat_sum"]
    out["bal_est"] = out["bal_est"].clip(lower=0)
    out["asof"] = asof
    out["known_date"] = last_known
    out["gap_days"] = len(gap_dates)
    out = out.reset_index()
    out.to_csv(ESTIMATE_CSV, index=False, encoding="utf-8-sig")
    log(f"추정 저장: {ESTIMATE_CSV.name} {len(out)}종목 "
        f"(확정 {last_known} → 추정 {asof}, 보간 {len(gap_dates)}거래일)")
    log(f"추정 경로 저장: {EST_PATH_CSV.name} {len(path):,}행 "
        f"({', '.join(gap_dates) if gap_dates else '없음'})")
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--window", type=int, default=60, help="회귀 표본 거래일 수 (20~60)")
    ap.add_argument("--min-obs", type=int, default=20, help="종목별 최소 표본")
    ap.add_argument("--min-r2", type=float, default=0.05,
                    help="이 미만이면 풀링 계수로 폴백")
    ap.add_argument("--asof", default=None, help="추정 기준일 YYYYMMDD")
    a = ap.parse_args()

    panel = build_panel()
    coef = fit_all(panel, a.window, a.min_obs, a.min_r2)
    est = estimate(panel, coef, a.asof)
    print(est.sort_values("bal_est", ascending=False).head(10).to_string(index=False))


if __name__ == "__main__":
    main()
