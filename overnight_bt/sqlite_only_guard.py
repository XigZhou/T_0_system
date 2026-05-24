from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Iterator

_TRUTHY = {"1", "true", "yes", "y", "on", "enabled", "sqlite", "sqlite-only"}
_ENV_NAME = "T0_SQLITE_ONLY"


def is_sqlite_only_enabled() -> bool:
    return str(os.environ.get(_ENV_NAME, "")).strip().lower() in _TRUTHY


def assert_sqlite_only_allowed(source: str, detail: str = "") -> None:
    if not is_sqlite_only_enabled():
        return
    message = f"SQLite-only mode blocks legacy source: {source}"
    clean_detail = str(detail or "").strip()
    if clean_detail:
        message = f"{message} ({clean_detail})"
    raise RuntimeError(message)


@contextmanager
def sqlite_only_disabled() -> Iterator[None]:
    previous = os.environ.get(_ENV_NAME)
    os.environ[_ENV_NAME] = "0"
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop(_ENV_NAME, None)
        else:
            os.environ[_ENV_NAME] = previous
