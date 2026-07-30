# -*- coding: utf-8 -*-
"""거래일 대비 공매도 잔고/거래량 수집 커버리지와 결측 구간을 보고한다."""
from __future__ import annotations

import pandas as pd

from common import DATA, SHORT_BAL_CSV, SHORT_VOL_CSV

prices = pd.read_csv(DATA / "prices.csv", dtype={"date": str}, usecols=["date"])
tdays = sorted(prices["date"].unique())
print(f"거래일(시세 기준): {len(tdays)}일  {tdays[0]} ~ {tdays[-1]}\n")


def report(name, path):
    if not path.exists():
        print(f"{name}: 없음\n")
        return set()
    d = pd.read_csv(path, dtype={"date": str, "code": str}, usecols=["date"])
    have = set(d["date"].unique())
    print(f"{name}: {len(have)}일  {min(have)} ~ {max(have)}")
    miss = [t for t in tdays if t not in have and t >= min(have)]
    if miss:
        # 연속 구간으로 압축
        runs, start, prev = [], miss[0], miss[0]
        for m in miss[1:]:
            if tdays.index(m) == tdays.index(prev) + 1:
                prev = m
                continue
            runs.append((start, prev))
            start = prev = m
        runs.append((start, prev))
        print(f"  결측 {len(miss)}일:")
        for a, b in runs:
            n = tdays.index(b) - tdays.index(a) + 1
            print(f"    {a} ~ {b}  ({n}일)")
    else:
        print("  결측 없음")
    print()
    return have


bal = report("공매도 잔고", SHORT_BAL_CSV)
vol = report("공매도 거래량", SHORT_VOL_CSV)

both = sorted(bal & vol)
print(f"잔고∩거래량 겹치는 거래일: {len(both)}일" + (f"  {both[0]} ~ {both[-1]}" if both else ""))
