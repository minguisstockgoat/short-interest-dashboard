# -*- coding: utf-8 -*-
"""공개 저장소에 올리기 전, 커밋 대상 파일에 민감정보가 있는지 점검한다.

.gitignore를 존중해 git이 실제로 추적할 파일만 검사한다.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# 실제 값 기반 패턴 (환경변수에서 읽어 하드코딩 방지)
LIVE = {k: v for k, v in {
    "KRX_API_KEY": os.environ.get("KRX_API_KEY"),
    "DART_API_KEY": os.environ.get("DART_API_KEY"),
    "TELEGRAM_BOT_TOKEN": os.environ.get("TELEGRAM_BOT_TOKEN"),
}.items() if v}
# KRX 로그인은 네이버 SSO 라 계정을 .env 에 두지 않는다 — 검사할 값 자체가 없다.

PATTERNS = [
    ("이메일", re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")),
    ("GitHub 토큰", re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}")),
    ("윈도우 사용자 경로", re.compile(r"C:\\+Users\\+[A-Za-z0-9_.-]+")),
    # 하이픈 표기만 잡는다. 하이픈 없는 13자리는 시가총액 등과 구분이 안 돼 오탐뿐이다.
    ("주민/사업자번호꼴", re.compile(r"\b\d{6}-[1-4]\d{6}\b|\b\d{3}-\d{2}-\d{5}\b")),
    ("JSESSIONID 값", re.compile(r"JSESSIONID\s*[=:]\s*[A-Za-z0-9._-]{10,}")),
    ("비밀번호 대입", re.compile(r"(?i)(password|passwd|\bpw)\s*=\s*[\"'][^\"']{3,}[\"']")),
]

ALLOW_EMAIL = {"noreply@", "example.com"}


def tracked_files() -> list[Path]:
    out = subprocess.run(["git", "ls-files", "-co", "--exclude-standard"],
                         cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
    files = []
    for line in out.stdout.splitlines():
        p = ROOT / line.strip()
        if p.is_file():
            files.append(p)
    return files


def main() -> int:
    files = tracked_files()
    print(f"검사 대상 {len(files)}개 파일 (.gitignore 반영)\n")
    hits = 0
    for p in files:
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        rel = p.relative_to(ROOT)

        for name, val in LIVE.items():
            if val and val in text:
                print(f"  [위험] {rel}: 환경변수 {name} 의 실제 값이 포함됨")
                hits += 1

        for label, rx in PATTERNS:
            for m in set(rx.findall(text)):
                s = m if isinstance(m, str) else m[0]
                if label == "이메일" and any(a in s for a in ALLOW_EMAIL):
                    continue
                print(f"  [확인] {rel}: {label} → {s[:70]}")
                hits += 1

    print()
    if hits == 0:
        print("민감정보 미발견 — 공개 저장소 업로드 가능")
    else:
        print(f"{hits}건 검토 필요 — 위 항목을 확인하고 필요하면 제거하세요")
    return 0


if __name__ == "__main__":
    sys.exit(main())
