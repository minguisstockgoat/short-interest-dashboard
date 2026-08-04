# -*- coding: utf-8 -*-
"""Fetch the free daily 5Y CDS settlement-price table from ICE Clear Credit."""
from __future__ import annotations

import argparse

import pandas as pd
import requests

from common import DATA, log

URL = "https://status.ice.com/api/cds-settlement-prices/icc-single-names"
OUT = DATA / "ice_cds.csv"
TARGETS = {
    "ORCLE": {"entity": "Oracle", "coupon_bp": 100},
    "COREWEI": {"entity": "CoreWeave", "coupon_bp": 500},
}
COLUMNS = ["clearing_date", "entity", "ticker", "name", "instrument_name",
           "coupon_bp", "eod_price"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--timeout", type=int, default=30)
    args = ap.parse_args()
    response = requests.get(URL, headers={"Accept": "application/json"}, timeout=args.timeout)
    response.raise_for_status()

    picked = []
    for row in response.json():
        instrument = str(row.get("instrumentName", ""))
        ticker = instrument.split(".", 1)[0]
        target = TARGETS.get(ticker)
        if not target or ".SNRFOR.USD." not in instrument:
            continue
        picked.append({
            "clearing_date": str(row["clearingDate"]), "entity": target["entity"],
            "ticker": ticker, "name": str(row.get("name", "")),
            "instrument_name": instrument, "coupon_bp": target["coupon_bp"],
            "eod_price": float(row["eodPrice"]),
        })
    if len(picked) != len(TARGETS):
        raise RuntimeError("ICE CDS targets incomplete: " + ", ".join(r["ticker"] for r in picked))

    fresh = pd.DataFrame(picked, columns=COLUMNS)
    if OUT.exists():
        old = pd.read_csv(OUT, dtype={"clearing_date": str, "ticker": str})
        fresh = pd.concat([old, fresh], ignore_index=True)
        fresh = fresh.drop_duplicates(["clearing_date", "ticker"], keep="last")
    fresh = fresh.sort_values(["clearing_date", "ticker"])
    fresh.to_csv(OUT, index=False, encoding="utf-8")
    log("ICE CDS " + ", ".join(
        f"{r['entity']}={r['eod_price']:.4f} ({r['clearing_date']})" for r in picked))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
