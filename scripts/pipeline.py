# -*- coding: utf-8 -*-
"""일일 갱신 파이프라인 (Windows / macOS 공통).

  python scripts/pipeline.py                 # 전체 갱신
  python scripts/pipeline.py --deploy        # 갱신 후 docs/ 커밋·푸시
  python scripts/pipeline.py --skip-krx-short  # KRX 공매도 건너뛰기
  python scripts/pipeline.py --days 14       # 시세·공매도 보강 기간

KRX 공매도(잔고/거래량)만 로그인 세션이 필요하다. 세션이 없으면 그 단계를
자동으로 건너뛰고 나머지(시세·유동주식수·대차잔고)를 갱신한 뒤 로그에 남긴다.
"""
from __future__ import annotations

import argparse
import datetime as dt
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
DOCS = ROOT / "docs"
LOGS = ROOT / "logs"
PY = sys.executable


def log(msg: str, *, head: bool = False) -> None:
    ts = dt.datetime.now().strftime("%H:%M:%S")
    line = f"\n=== {msg} ===" if head else f"[{ts}] {msg}"
    print(line, flush=True)
    LOGS.mkdir(exist_ok=True)
    with open(LOGS / f"pipeline_{dt.date.today():%Y%m%d}.log", "a",
              encoding="utf-8") as f:
        f.write(line + "\n")


def run(args: list[str], *, check: bool = True, cwd: Path = ROOT) -> int:
    """하위 스크립트를 현재 파이썬으로 실행하고 출력을 흘려보낸다."""
    printable = " ".join(str(a) for a in args)
    log(f"$ {printable}")
    p = subprocess.run([str(a) for a in args], cwd=str(cwd))
    if check and p.returncode != 0:
        raise SystemExit(f"실패(exit={p.returncode}): {printable}")
    return p.returncode


def git(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    p = subprocess.run(["git", *args], cwd=str(ROOT), capture_output=True,
                       text=True, encoding="utf-8", errors="replace")
    if check and p.returncode != 0:
        raise SystemExit(f"git {' '.join(args)} 실패: {p.stderr.strip()}")
    return p


def krx_session_ok() -> bool:
    p = subprocess.run([PY, str(SCRIPTS / "krx_session.py")], cwd=str(ROOT),
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace")
    return p.returncode == 0 and "사용 가능" in (p.stdout or "")


def latest_price_date() -> str:
    import pandas as pd
    d = pd.read_csv(ROOT / "data" / "prices.csv", dtype={"date": str},
                    usecols=["date"])
    return sorted(d["date"].unique())[-1]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=7, help="보강 기간(달력일)")
    ap.add_argument("--loan-days", type=int, default=210)
    ap.add_argument("--skip-krx-short", action="store_true")
    ap.add_argument("--skip-float", action="store_true")
    ap.add_argument("--deploy", action="store_true", help="docs/ 커밋·푸시")
    a = ap.parse_args()

    today = dt.date.today()
    end = today.strftime("%Y%m%d")
    start = (today - dt.timedelta(days=a.days * 2)).strftime("%Y%m%d")
    loan_start = (today - dt.timedelta(days=a.loan_days)).strftime("%Y%m%d")

    log("일일 갱신 시작", head=True)
    log(f"플랫폼 {sys.platform} / 파이썬 {sys.version.split()[0]} / 기간 {start}~{end}")

    log("1. KRX OPEN API 시세·상장주식수", head=True)
    run([PY, SCRIPTS / "krx_open.py", "--start", start, "--end", end,
         "--workers", "4"])

    log("2. 종목 마스터·유니버스", head=True)
    run([PY, SCRIPTS / "build_master.py", "--date", latest_price_date()])

    if a.skip_float:
        log("3. 유동주식수 건너뜀", head=True)
    else:
        log("3. FnGuide 유동주식수", head=True)
        run([PY, SCRIPTS / "fnguide_float.py", "--workers", "8",
             "--max-age-days", "7"], check=False)

    log("4. KOFIA 대차잔고", head=True)
    run([PY, SCRIPTS / "kofia_loan.py", "--start", loan_start, "--end", end,
         "--workers", "4", "--no-cache"], check=False)

    log("5. KRX 공매도 잔고·거래량", head=True)
    if a.skip_krx_short:
        log("건너뜀(--skip-krx-short) — 기존 값 유지")
    elif not krx_session_ok():
        log("KRX 로그인 세션 없음 — 공매도는 직전 값 유지")
        log("  크롬을 로그인 상태로 띄워두면 다음 실행에 자동 수집됩니다.")
    else:
        run([PY, SCRIPTS / "krx_short.py", "--start", start, "--end", end,
             "--workers", "2"], check=False)

    log("6. 커버리지 점검", head=True)
    run([PY, SCRIPTS / "coverage.py"], check=False)

    log("7. 회귀 추정(alpha·beta) 및 D일 추정잔고", head=True)
    run([PY, SCRIPTS / "estimate.py", "--window", "60", "--min-obs", "20",
         "--min-r2", "0.05"])

    log("8. 대시보드 데이터 생성", head=True)
    run([PY, SCRIPTS / "build_dashboard.py"])

    # --- 산출물 검증 ---------------------------------------------------
    out = DOCS / "dashboard_data.json"
    if not out.exists():
        log("중단: dashboard_data.json 없음")
        return 1
    size = out.stat().st_size
    if size < 500_000:
        log(f"중단: dashboard_data.json 이 비정상적으로 작음 ({size:,} bytes)")
        return 1
    import json
    meta = json.loads(out.read_text(encoding="utf-8"))["meta"]
    log(f"기준일 {meta['asof']} / 확정일 {meta['knownDate']} / "
        f"{meta['universe']}종목 / {size/1e6:.2f} MB")

    # --- 배포 -----------------------------------------------------------
    if not a.deploy:
        log("배포 생략(--deploy 미지정)")
        return 0

    if not git("status", "--porcelain", "--", "docs").stdout.strip():
        log("docs 변경 없음 — 배포 생략")
        return 0

    git("add", "docs")
    git("commit", "-q", "-m",
        f"데이터 갱신 {meta['asof']} (확정 {meta['knownDate']})")
    r = git("push", "-q", "origin", "main", check=False)
    if r.returncode != 0:
        log(f"푸시 실패: {r.stderr.strip()[:200]}")
        return 1
    log("배포 완료 → https://minguisstockgoat.github.io/short-interest-dashboard/")

    for old in sorted(LOGS.glob("pipeline_*.log"))[:-30]:
        old.unlink(missing_ok=True)
    log("완료", head=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
