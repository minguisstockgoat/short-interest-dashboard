# -*- coding: utf-8 -*-
"""FnGuide Company Guide Snapshot에서 종목별 유동주식수/유동비율을 수집한다.

companyguide 스킬과 동일한 엔드포인트(wcomp.fnguide.com, 인증 불필요)를 쓰되,
전종목 대량 수집을 위해 필요한 필드만 정규식으로 뽑고 병렬화·캐싱한다.
유동주식수는 자주 바뀌지 않으므로 --max-age-days 이내 캐시는 재사용한다.
"""
from __future__ import annotations

import argparse
import datetime as dt
import re
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd

from common import DATA, FLOAT_CSV, log

UNIVERSE_CSV = DATA / "universe.csv"

BASE = "https://wcomp.fnguide.com"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/125.0 Safari/537.36",
    "Referer": BASE + "/",
    "Accept-Language": "ko-KR,ko;q=0.9",
}

TAG_RE = re.compile(r"<[^>]+>")
WS_RE = re.compile(r"[ \t\r\f\v]+")
# "유동주식수/비율 (보통주)" 뒤에 "4,420,816,819/ 75.62" 형태로 등장
FLOAT_RE = re.compile(
    r"유동주식수\s*/\s*비율\s*\(보통주\)\s*([\d,]+)\s*/\s*([\d.]+)")
# 상장주식수(보통주) 백업용
LIST_RE = re.compile(r"상장주식수\s*\(보통주\)\s*([\d,]+)")

_lock = threading.Lock()
_progress = {"done": 0, "ok": 0}


def _text(html: str) -> str:
    html = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.S | re.I)
    html = re.sub(r"<br\s*/?>", "\n", html, flags=re.I)
    html = re.sub(r"</(td|th|tr|div|p|li)>", "\n", html, flags=re.I)
    txt = TAG_RE.sub(" ", html)
    txt = (txt.replace("&nbsp;", " ").replace("&amp;", "&")
              .replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"'))
    txt = WS_RE.sub(" ", txt)
    return re.sub(r"\n\s*\n+", "\n", txt)


def fetch_one(code: str, retries: int = 3) -> dict | None:
    url = f"{BASE}/CompanyInfo/Snapshot?cmp_cd={code}"
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=30) as r:
                html = r.read().decode("utf-8", errors="replace")
            txt = _text(html)
            m = FLOAT_RE.search(txt)
            if not m:
                # 줄바꿈이 끼는 레이아웃 대비: 라벨 이후 200자 내 "숫자/숫자" 패턴 탐색
                idx = txt.find("유동주식수/비율 (보통주)")
                if idx == -1:
                    idx = txt.find("유동주식수/비율")
                if idx != -1:
                    m = re.search(r"([\d,]{4,})\s*/\s*([\d.]+)", txt[idx:idx + 300])
            if not m:
                return None
            shares = int(m.group(1).replace(",", ""))
            ratio = float(m.group(2))
            lm = LIST_RE.search(txt)
            listed = int(lm.group(1).replace(",", "")) if lm else None
            return {"code": code, "float_shares": shares, "float_ratio": ratio,
                    "fnguide_list_shares": listed,
                    "fetched_at": dt.date.today().strftime("%Y%m%d")}
        except Exception:
            if attempt < retries - 1:
                time.sleep(1.0 * (attempt + 1))
    return None


def _worker(code: str, total: int) -> dict | None:
    res = fetch_one(code)
    with _lock:
        _progress["done"] += 1
        if res:
            _progress["ok"] += 1
        if _progress["done"] % 200 == 0:
            log(f"  진행 {_progress['done']}/{total} (성공 {_progress['ok']})")
    return res


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=12)
    ap.add_argument("--max-age-days", type=int, default=7,
                    help="이 일수 이내에 받은 캐시는 재사용")
    ap.add_argument("--limit", type=int, default=0, help="테스트용 상위 N종목만")
    a = ap.parse_args()

    if not UNIVERSE_CSV.exists():
        raise SystemExit(f"{UNIVERSE_CSV} 가 없습니다. 먼저 build_master.py 를 실행하세요.")
    master = pd.read_csv(UNIVERSE_CSV, dtype={"code": str})
    codes = master["code"].astype(str).str.zfill(6).tolist()
    if a.limit:
        codes = codes[:a.limit]

    cached: dict[str, dict] = {}
    if FLOAT_CSV.exists():
        old = pd.read_csv(FLOAT_CSV, dtype={"code": str, "fetched_at": str})
        cutoff = (dt.date.today() - dt.timedelta(days=a.max_age_days)).strftime("%Y%m%d")
        for rec in old.to_dict("records"):
            rec["code"] = str(rec["code"]).zfill(6)
            if str(rec.get("fetched_at", "")) >= cutoff:
                cached[rec["code"]] = rec

    todo = [c for c in codes if c not in cached]
    log(f"유동주식수 수집: 전체 {len(codes)}종목, 캐시 재사용 {len(codes) - len(todo)}, 신규 {len(todo)}")

    results = list(cached.values())
    if todo:
        with ThreadPoolExecutor(max_workers=a.workers) as ex:
            futs = [ex.submit(_worker, c, len(todo)) for c in todo]
            for f in as_completed(futs):
                r = f.result()
                if r:
                    results.append(r)

    if not results:
        log("수집 결과 없음")
        return
    df = pd.DataFrame(results).drop_duplicates(subset=["code"], keep="last")
    df["code"] = df["code"].astype(str).str.zfill(6)
    df = df.sort_values("code")
    df.to_csv(FLOAT_CSV, index=False, encoding="utf-8-sig")
    miss = len(codes) - df["code"].isin(codes).sum()
    log(f"저장: {FLOAT_CSV.name} {len(df):,}종목 (마스터 대비 미수집 {miss}종목)")


if __name__ == "__main__":
    main()
