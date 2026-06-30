from __future__ import annotations

import logging
from pathlib import Path

import pytest
import shiny.bookmark._global as bookmark_global
from shinychat._history_bookmark import delete_bookmark_state, extract_state_id


@pytest.fixture(autouse=True)
def reset_globals(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(bookmark_global, "_default_bookmark_restore_dir_fn", None)


def test_extract_state_id_finds_param():
    assert extract_state_id("/app?_state_id_=abc123") == "abc123"


def test_extract_state_id_missing_returns_none():
    assert extract_state_id("/app") is None


@pytest.mark.anyio
async def test_delete_bookmark_state_silent_when_machinery_not_registered():
    # No restore-dir fn registered: should no-op without raising.
    await delete_bookmark_state("abc123")


@pytest.mark.anyio
async def test_delete_bookmark_state_silent_on_missing_private_api(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.delattr(bookmark_global, "get_bookmark_restore_dir_fn")
    await delete_bookmark_state("abc123")  # must not raise


@pytest.mark.anyio
async def test_delete_bookmark_state_logs_unexpected_errors(
    caplog: pytest.LogCaptureFixture,
):
    from shiny.bookmark import set_global_restore_dir_fn

    def boom(state_id: str) -> Path:
        raise ValueError("boom")

    set_global_restore_dir_fn(boom)

    with caplog.at_level(logging.WARNING):
        await delete_bookmark_state("abc123")  # must not raise

    assert "boom" in caplog.text
    assert any(r.levelno == logging.WARNING for r in caplog.records)


@pytest.mark.anyio
async def test_delete_bookmark_state_removes_directory(tmp_path: Path):
    from shiny.bookmark import set_global_restore_dir_fn

    target = tmp_path / "state-dir"
    target.mkdir()
    (target / "data.json").write_text("{}")

    set_global_restore_dir_fn(lambda state_id: target)

    await delete_bookmark_state("abc123")

    assert not target.exists()
