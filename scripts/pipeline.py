# -*- coding: utf-8 -*-
"""일일 갱신 파이프라인 (Windows / macOS 공통).

  python scripts/pipeline.py                 # 전체 갱신
  python scripts/pipeline.py --deploy        # 갱신 후 docs/ 커밋·푸시
  python scripts/pipeline.py --skip-open       # 시세 수집 건너뛰기 (OPEN API 키 없을 때)
  python scripts/pipeline.py --skip-krx-short  # KRX 공매도 건너뛰기
  python scripts/pipeline.py --days 14       # 시세·공매도 보강 기간

KRX 공매도(잔고/거래량)만 로그인 세션이 필요하다. 세션이 없으면 .env 계정으로
자동 로그인을 한 번 시도하고, 그래도 안 되면 그 단계만 건너뛴 뒤 텔레그램으로
알린다(조용히 낡은 값을 배포하지 않는다).
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
DOCS = ROOT / "docs"
LOGS = ROOT / "logs"
DATA = ROOT / "data"
STATUS = DATA / ".pipeline_status.json"
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


def set_status(state: str, **extra) -> None:
    """진행 상태를 파일로 남긴다 — 대시보드 '수동 갱신' 버튼이 이걸 읽어 보여준다."""
    DATA.mkdir(parents=True, exist_ok=True)
    try:
        payload = {"state": state,
                   "at": dt.datetime.now().isoformat(timespec="seconds"), **extra}
        STATUS.write_text(json.dumps(payload, ensure_ascii=False),
                          encoding="utf-8")
    except OSError:
        pass


def latest_price_date() -> str:
    import pandas as pd
    d = pd.read_csv(ROOT / "data" / "prices.csv", dtype={"date": str},
                    usecols=["date"])
    return sorted(d["date"].unique())[-1]


def run_pipeline(a) -> int:
    today = dt.date.today()
    end = today.strftime("%Y%m%d")
    start = (today - dt.timedelta(days=a.days * 2)).strftime("%Y%m%d")
    loan_start = (today - dt.timedelta(days=a.loan_days)).strftime("%Y%m%d")

    log("일일 갱신 시작", head=True)
    log(f"플랫폼 {sys.platform} / 파이썬 {sys.version.split()[0]} / 기간 {start}~{end}")
    set_status("running", step="1/8 시세", source=a.source)

    # 1·2단계는 둘 다 KRX OPEN API(KRX_API_KEY)를 쓴다. 키가 없으면 함께 건너뛴다.
    log("1. KRX OPEN API 시세·상장주식수", head=True)
    if a.skip_open:
        log("건너뜀(--skip-open) — 기존 prices.csv 로 진행")
    else:
        run([PY, SCRIPTS / "krx_open.py", "--start", start, "--end", end,
             "--workers", "4"])

    log("2. 종목 마스터·유니버스", head=True)
    if a.skip_open:
        log("건너뜀(--skip-open) — 기존 master.csv / universe.csv 유지")
    else:
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
    set_status("running", step="5/8 공매도(KRX)", source=a.source)
    if a.skip_krx_short:
        log("건너뜀(--skip-krx-short) — 기존 값 유지")
    else:
        import krx_login
        if krx_login.ensure_login():
            run([PY, SCRIPTS / "krx_short.py", "--start", start, "--end", end,
                 "--workers", "2"], check=False)
        else:
            # ensure_login 이 이미 사유별로 텔레그램을 보냈다. 여기선 로그만.
            log("KRX 로그인 세션 확보 실패 — 공매도는 직전 값 유지")

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
    meta = json.loads(out.read_text(encoding="utf-8"))["meta"]
    log(f"기준일 {meta['asof']} / 확정일 {meta['knownDate']} / "
        f"{meta['universe']}종목 / {size/1e6:.2f} MB")

    # --- 공매도 신선도 경보 ---------------------------------------------
    # 스케줄러가 돌아도 KRX 단계만 조용히 멈추는 게 실제로 겪은 사고였다.
    # 정상 지연(T+2)을 넘겨 밀리면 사람에게 알린다.
    stale = meta.get("shortStaleDays")
    if stale:
        import notify
        notify.send(
            f"⚠ 공매도 잔고가 {stale}거래일 더 밀려 있습니다.\n"
            f"확정일 {meta['knownDate']} / 기준일 {meta['asof']}\n"
            f"KRX 수집이 며칠째 실패하고 있을 수 있습니다. "
            f"`krx_login.py --status` 로 세션 상태를 확인해 주세요.",
            dedupe="short-stale", cooldown_h=20)
    else:
        import notify
        notify.clear("short-stale")

    # --- 배포 -----------------------------------------------------------
    if not a.deploy:
        log("배포 생략(--deploy 미지정)")
        return 0

    if not git("status", "--porcelain", "--", "docs").stdout.strip():
        log("docs 변경 없음 — 배포 생략")
        return 0

    # 맥미니와 이 컴퓨터가 번갈아 푸시하므로, 뒤처진 채 커밋하면 푸시가 계속 막힌다
    r = git("pull", "--rebase", "--autostash", "-q", "origin", "main", check=False)
    if r.returncode != 0:
        log(f"pull 실패(계속 진행): {r.stderr.strip()[:200]}")

    # 반드시 docs 만 커밋한다. `add docs` 뒤 경로 없이 commit 하면 인덱스에 올라와
    # 있던 다른 변경(특히 --autostash 가 복원한 로컬 수정)까지 함께 커밋돼,
    # 검토 안 된 코드가 "데이터 갱신" 이름으로 푸시된다. 실제로 한 번 겪었다.
    git("commit", "-q", "-m",
        f"데이터 갱신 {meta['asof']} (확정 {meta['knownDate']})", "--", "docs")
    r = git("push", "-q", "origin", "main", check=False)
    if r.returncode != 0:
        log(f"푸시 실패: {r.stderr.strip()[:200]}")
        return 1
    log("배포 완료 → https://minguisstockgoat.github.io/short-interest-dashboard/")

    for old in sorted(LOGS.glob("pipeline_*.log"))[:-30]:
        old.unlink(missing_ok=True)
    log("완료", head=True)
    return 0


def _meta_summary() -> dict:
    """상태 파일에 실어 보낼 최신 기준일 요약."""
    out = DOCS / "dashboard_data.json"
    try:
        m = json.loads(out.read_text(encoding="utf-8"))["meta"]
        return {k: m.get(k) for k in
                ("asof", "knownDate", "shortStaleDays", "generatedAt")}
    except (OSError, ValueError, KeyError):
        return {}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=7, help="보강 기간(달력일)")
    ap.add_argument("--loan-days", type=int, default=210)
    ap.add_argument("--skip-open", action="store_true",
                    help="OPEN API 단계(시세·마스터) 생략 — 기존 CSV로 진행"
                         " (기준일이 기존 prices.csv 마지막 날짜에 묶인다)")
    ap.add_argument("--skip-krx-short", action="store_true")
    ap.add_argument("--skip-float", action="store_true")
    ap.add_argument("--deploy", action="store_true", help="docs/ 커밋·푸시")
    ap.add_argument("--source", default="schedule",
                    help="실행 출처 (schedule/manual) — 상태 표시에만 쓰인다")
    a = ap.parse_args()

    try:
        code = run_pipeline(a)
    except SystemExit as e:                      # run(check=True) 실패
        set_status("failed", error=str(e), source=a.source, **_meta_summary())
        import notify
        notify.send(f"❌ 갱신 파이프라인이 중단됐습니다.\n{e}",
                    dedupe="pipeline-failed", cooldown_h=6)
        raise
    except Exception as e:
        set_status("failed", error=f"{type(e).__name__}: {e}", source=a.source,
                   **_meta_summary())
        import notify
        notify.send(f"❌ 갱신 파이프라인 예외: {type(e).__name__} {e}",
                    dedupe="pipeline-failed", cooldown_h=6)
        raise

    set_status("done" if code == 0 else "failed", exit=code, source=a.source,
               **_meta_summary())
    return code


if __name__ == "__main__":
    sys.exit(main())
