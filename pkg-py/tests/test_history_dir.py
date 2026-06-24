from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
import shiny.bookmark._global as bookmark_global
from shinychat._history_store import resolve_history_dir


@pytest.fixture(autouse=True)
def reset_globals(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("CONNECT_CONTENT_DATA_DIR", raising=False)
    monkeypatch.setattr(bookmark_global, "_default_bookmark_save_dir_fn", None)


def test_connect_data_dir_wins(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setenv("CONNECT_CONTENT_DATA_DIR", str(tmp_path))
    assert (
        asyncio.run(resolve_history_dir())
        == tmp_path / "shinychat-conversations"
    )


def test_bookmark_machinery_used_when_registered(tmp_path: Path):
    from shiny.bookmark import set_global_save_dir_fn

    def save_dir(id: str) -> Path:
        d = tmp_path / "bm" / id
        d.mkdir(parents=True, exist_ok=True)
        return d

    set_global_save_dir_fn(save_dir)
    assert (
        asyncio.run(resolve_history_dir())
        == tmp_path / "bm" / "shinychat-conversations"
    )


def test_env_var_beats_bookmark_machinery(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    from shiny.bookmark import set_global_save_dir_fn

    set_global_save_dir_fn(lambda bm_id: tmp_path / "bm" / bm_id)
    monkeypatch.setenv("CONNECT_CONTENT_DATA_DIR", str(tmp_path / "env"))
    assert (
        asyncio.run(resolve_history_dir())
        == tmp_path / "env" / "shinychat-conversations"
    )


def test_local_fallback():
    assert (
        asyncio.run(resolve_history_dir())
        == Path(".shinychat") / "conversations"
    )
