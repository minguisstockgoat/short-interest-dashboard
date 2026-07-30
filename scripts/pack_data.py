# -*- coding: utf-8 -*-
"""수집 데이터를 다른 PC(맥미니 등)로 옮기기 위한 아카이브를 만든다.

  python scripts/pack_data.py            # 필수 CSV만 (권장, 가벼움)
  python scripts/pack_data.py --with-raw # 원본 캐시까지 (재수집 완전 불필요)
  python scripts/pack_data.py --unpack bootstrap_data.tar.gz   # 맥에서 풀기

맥에서 처음부터 수집하면 KRX에 수백 건을 요청하게 되어 IP 차단 위험이 있다.
이 아카이브를 옮기면 재수집 없이 바로 이어서 돌릴 수 있다.

원본 캐시(data/raw)에는 공매도 대량보유자 공시의 제3자 성명·주소가 포함될 수
있으므로 --with-raw 산출물은 외부에 공개하지 말 것.
"""
from __future__ import annotations

import argparse
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

# 파이프라인이 이어서 돌기 위해 반드시 필요한 산출물
ESSENTIAL = [
    "prices.csv",        # 시세·상장주식수 (302거래일)
    "master.csv",
    "universe.csv",
    "free_float.csv",    # 유동주식수
    "short_balance.csv", # 공매도 순보유잔고 (재수집이 가장 비쌈)
    "short_volume.csv",  # 공매도 거래량
    "loan_balance.csv",  # 대차잔고 (KOFIA — 재수집 저렴하지만 포함)
]
# short_panel / short_coef / short_estimate 는 estimate.py 가 매번 다시 만든다.


def pack(out: Path, with_raw: bool) -> None:
    if not DATA.exists():
        raise SystemExit("data/ 폴더가 없습니다.")
    members: list[Path] = []
    for name in ESSENTIAL:
        p = DATA / name
        if p.exists():
            members.append(p)
        else:
            print(f"  ! 없음(건너뜀): {name}")
    if with_raw:
        raw = DATA / "raw"
        if raw.exists():
            members.extend(sorted(raw.rglob("*")))

    with tarfile.open(out, "w:gz") as tf:
        for p in members:
            if p.is_file():
                tf.add(p, arcname=str(p.relative_to(ROOT)))

    mb = out.stat().st_size / 1e6
    print(f"\n생성: {out}  ({mb:.1f} MB, 파일 {sum(1 for m in members if m.is_file()):,}개)")
    print("\n맥미니로 옮긴 뒤 저장소 루트에서:")
    print(f"  tar -xzf {out.name}")
    print("  bash mac/doctor.sh")
    if with_raw:
        print("\n주의: 원본 캐시에 제3자 성명·주소가 포함될 수 있습니다. 외부 공개 금지.")


def unpack(archive: Path) -> None:
    if not archive.exists():
        raise SystemExit(f"파일이 없습니다: {archive}")
    with tarfile.open(archive, "r:gz") as tf:
        names = tf.getnames()
        bad = [n for n in names if n.startswith("/") or ".." in Path(n).parts]
        if bad:
            raise SystemExit(f"경로가 안전하지 않은 항목이 있어 중단합니다: {bad[:3]}")
        tf.extractall(ROOT)
    print(f"복원 완료: {len(names):,}개 → {ROOT}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="bootstrap_data.tar.gz")
    ap.add_argument("--with-raw", action="store_true",
                    help="원본 캐시까지 포함 (용량 큼, 외부 공개 금지)")
    ap.add_argument("--unpack", metavar="ARCHIVE", help="아카이브 풀기")
    a = ap.parse_args()

    if a.unpack:
        unpack(Path(a.unpack))
    else:
        pack(ROOT / a.out, a.with_raw)


if __name__ == "__main__":
    main()
