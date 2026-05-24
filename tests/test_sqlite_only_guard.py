from __future__ import annotations

import pytest

from overnight_bt.sqlite_only_guard import assert_sqlite_only_allowed, is_sqlite_only_enabled, sqlite_only_disabled


def test_sqlite_only_flag_defaults_to_disabled(monkeypatch):
    monkeypatch.delenv("T0_SQLITE_ONLY", raising=False)

    assert is_sqlite_only_enabled() is False
    assert_sqlite_only_allowed("legacy csv")


def test_sqlite_only_flag_blocks_legacy_source(monkeypatch):
    monkeypatch.setenv("T0_SQLITE_ONLY", "1")

    with pytest.raises(RuntimeError, match="SQLite-only mode blocks legacy source: legacy csv"):
        assert_sqlite_only_allowed("legacy csv", "data_bundle/processed_qfq")


def test_sqlite_only_disabled_context_restores_environment(monkeypatch):
    monkeypatch.setenv("T0_SQLITE_ONLY", "1")

    with sqlite_only_disabled():
        assert is_sqlite_only_enabled() is False
        assert_sqlite_only_allowed("legacy csv")

    assert is_sqlite_only_enabled() is True
