# -*- coding: utf-8 -*-
"""저장소 루트의 .env 와 중앙 키 저장소를 os.environ 에 얹는다.

launchd/작업 스케줄러는 로그인 셸 환경을 물려주지 않는다. 쉘 래퍼가 `source .env`
를 해주더라도 파이썬을 직접 실행하는 경로(수동 실행·에이전트)에서는 비어 있으므로,
common.py 가 import 시점에 한 번 호출해 어느 진입점에서든 동일하게 채운다.

우선순위는 명시적 export > 저장소 .env > 중앙 볼트(~/.config/secrets/keys.env).
KRX 계정처럼 여러 프로젝트가 함께 쓰는 값은 볼트에만 두고 저장소에는 복사하지
않는다 — .env 는 gitignore 되지만 사본이 늘어날수록 새어나갈 구멍도 늘어난다.
"""
from __future__ import annotations

import os
from pathlib import Path

ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
VAULT_PATH = Path.home() / ".config" / "secrets" / "keys.env"

_loaded = False


def load(path: Path = ENV_PATH, *, override: bool = False) -> dict[str, str]:
    """.env 와 (기본 경로일 때) 중앙 볼트를 환경에 반영하고, 읽은 값을 돌려준다."""
    global _loaded
    found = _load_file(path, override=override)
    if path == ENV_PATH:
        # 볼트는 빈 자리만 채운다 — 저장소 .env 가 항상 이긴다.
        found = {**_load_file(VAULT_PATH, override=False), **found}
    _loaded = True
    return found


def _load_file(path: Path, *, override: bool) -> dict[str, str]:
    found: dict[str, str] = {}
    if not path.exists():
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

    return found


def require(*keys: str) -> list[str]:
    """필수 환경변수를 읽고, 비어 있으면 어떤 키가 없는지 알려주며 중단한다."""
    if not _loaded:
        load()
    missing = [k for k in keys if not os.environ.get(k)]
    if missing:
        raise SystemExit(
            f"환경변수 누락: {', '.join(missing)}\n"
            f"  → {ENV_PATH} 또는 {VAULT_PATH} 에 값을 채우세요."
        )
    return [os.environ[k] for k in keys]


def get(key: str, default: str | None = None) -> str | None:
    if not _loaded:
        load()
    v = os.environ.get(key)
    return v if v else default
