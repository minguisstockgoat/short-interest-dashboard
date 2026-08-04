# -*- coding: utf-8 -*-
"""저장소 루트의 .env 를 os.environ 에 얹는다.

launchd/작업 스케줄러는 로그인 셸 환경을 물려주지 않는다. 쉘 래퍼가 `source .env`
를 해주더라도 파이썬을 직접 실행하는 경로(수동 실행·에이전트)에서는 비어 있으므로,
common.py 가 import 시점에 한 번 호출해 어느 진입점에서든 동일하게 채운다.

이미 환경에 있는 값은 덮어쓰지 않는다(명시적 export 가 파일보다 우선).
"""
from __future__ import annotations

import os
from pathlib import Path

ENV_PATH = Path(__file__).resolve().parent.parent / ".env"

_loaded = False


def load(path: Path = ENV_PATH, *, override: bool = False) -> dict[str, str]:
    """.env 를 파싱해 환경에 반영하고, 파일에서 읽은 값을 반환한다."""
    global _loaded
    found: dict[str, str] = {}
    if not path.exists():
        _loaded = True
        return found

    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        if "=" not in line:
            continue
        key, val = line.split("=", 1)
        key, val = key.strip(), val.strip()
        if not key:
            continue
        # 따옴표로 감싼 값 해제 (비밀번호에 #·공백이 들어갈 수 있어 인용을 권장)
        if len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
            val = val[1:-1]
        found[key] = val
        if override or not os.environ.get(key):
            os.environ[key] = val

    _loaded = True
    return found


def require(*keys: str) -> list[str]:
    """필수 환경변수를 읽고, 비어 있으면 어떤 키가 없는지 알려주며 중단한다."""
    if not _loaded:
        load()
    missing = [k for k in keys if not os.environ.get(k)]
    if missing:
        raise SystemExit(
            f"환경변수 누락: {', '.join(missing)}\n"
            f"  → {ENV_PATH} 에 값을 채우세요."
        )
    return [os.environ[k] for k in keys]


def get(key: str, default: str | None = None) -> str | None:
    if not _loaded:
        load()
    v = os.environ.get(key)
    return v if v else default
