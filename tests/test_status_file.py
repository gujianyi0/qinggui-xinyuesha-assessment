"""Regression: a locked status file must not take the native preview down.

Reproduces the 2026-11-10 one-hour soak failure where a transient
``PermissionError`` (WinError 5) from ``status.tmp -> status.json`` escaped
``report()``, stopped the supervisor and caused 58 consecutive ConnectErrors.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from backend.app.status_file import atomic_write_json, atomic_write_text


def _hold_replace(monkeypatch, failures: int):
    real_replace = os.replace
    calls = {"n": 0, "recovered": 0}

    def flaky(src, dst):
        calls["n"] += 1
        if calls["n"] <= failures:
            raise PermissionError(5, "Access is denied")
        calls["recovered"] += 1
        return real_replace(src, dst)

    monkeypatch.setattr("backend.app.status_file.os.replace", flaky)
    return calls


def test_transient_permission_error_is_retried_and_succeeds(tmp_path, monkeypatch):
    calls = _hold_replace(monkeypatch, failures=3)
    target = tmp_path / "status.json"
    assert atomic_write_text(target, "ok", attempts=6, delay=0) is True
    assert target.read_text(encoding="utf-8") == "ok"
    assert calls["recovered"] == 1
    assert calls["n"] == 4


def test_persistent_lock_returns_false_without_raising(tmp_path, monkeypatch):
    _hold_replace(monkeypatch, failures=99)
    target = tmp_path / "status.json"
    target.write_text("previous", encoding="utf-8")
    assert atomic_write_text(target, "new", attempts=4, delay=0) is False
    # 旧状态仍可读，服务继续运行。
    assert target.read_text(encoding="utf-8") == "previous"


def test_no_temp_files_left_behind_after_failure(tmp_path, monkeypatch):
    _hold_replace(monkeypatch, failures=99)
    target = tmp_path / "status.json"
    assert atomic_write_text(target, "x", attempts=3, delay=0) is False
    assert list(tmp_path.glob("*.tmp")) == []


def test_json_round_trip_and_atomic_visibility(tmp_path):
    target = tmp_path / "status.json"
    state = {"stage": "running", "worker": {"pid": 42, "restart_count": 1}}
    assert atomic_write_json(target, state) is True
    assert json.loads(target.read_text(encoding="utf-8")) == state
    assert list(tmp_path.iterdir()) == [target]


def test_concurrent_writers_do_not_clobber_each_others_temp_files(tmp_path, monkeypatch):
    real_replace = os.replace
    seen: list[str] = []

    def recording(src, dst):
        seen.append(Path(src).name)
        return real_replace(src, dst)

    monkeypatch.setattr("backend.app.status_file.os.replace", recording)
    target = tmp_path / "status.json"
    assert atomic_write_text(target, "a") is True
    assert atomic_write_text(target, "b") is True
    assert target.read_text(encoding="utf-8") == "b"
    assert len(set(seen)) == 2, "each attempt must use its own temporary file"


def test_write_error_does_not_escape_to_supervisor(tmp_path, monkeypatch):
    """The contract the supervisor relies on: no exception, ever."""
    _hold_replace(monkeypatch, failures=99)
    target = tmp_path / "status.json"
    try:
        result = atomic_write_json(target, {"stage": "running"}, attempts=3, delay=0)
    except Exception as error:  # pragma: no cover - regression guard
        pytest.fail(f"status write must not raise: {error!r}")
    assert result is False
