from __future__ import annotations

import logging
from pathlib import Path

import pytest
import shiny.bookmark._global as bookmark_global
from shinychat._history_store import resolve_history_dir


@pytest.fixture(autouse=True)
def reset_globals(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("CONNECT_CONTENT_DATA_DIR", raising=False)
    monkeypatch.setattr(bookmark_global, "_default_bookmark_save_dir_fn", None)
    monkeypatch.setattr(
        bookmark_global, "_default_bookmark_restore_dir_fn", None
    )


def register_connect_like_hooks(root: Path) -> None:
    """Mirror Posit Connect's write-once save/restore bookmark hooks."""
    from shiny.bookmark import set_global_restore_dir_fn, set_global_save_dir_fn

    def save_dir(id: str) -> Path:
        d = root / id
        if d.exists():
            raise RuntimeError(
                f"Directory {d} already exists; cannot overwrite existing bookmark directory."
            )
        d.mkdir(parents=True, exist_ok=True)
        return d

    def restore_dir(id: str) -> Path:
        d = root / id
        if not d.exists():
            raise RuntimeError(f"Directory {d} does not exist.")
        return d

    set_global_save_dir_fn(save_dir)
    set_global_restore_dir_fn(restore_dir)


@pytest.mark.anyio
async def test_connect_data_dir_wins(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    monkeypatch.setenv("CONNECT_CONTENT_DATA_DIR", str(tmp_path))
    assert await resolve_history_dir() == tmp_path / "shinychat-conversations"


@pytest.mark.anyio
async def test_bookmark_machinery_used_when_registered(tmp_path: Path):
    from shiny.bookmark import set_global_save_dir_fn

    def save_dir(id: str) -> Path:
        d = tmp_path / "bm" / id
        d.mkdir(parents=True, exist_ok=True)
        return d

    set_global_save_dir_fn(save_dir)
    assert (
        await resolve_history_dir()
        == tmp_path / "bm" / "shinychat-conversations"
    )


@pytest.mark.anyio
async def test_connect_like_hooks_survive_repeated_sessions(tmp_path: Path):
    register_connect_like_hooks(tmp_path / "bm")

    first = await resolve_history_dir()
    second = await resolve_history_dir()

    assert first == second == tmp_path / "bm" / "shinychat-conversations"
    assert first.is_dir()


@pytest.mark.anyio
async def test_connect_like_hooks_survive_lost_creation_race(tmp_path: Path):
    from shiny.bookmark import set_global_restore_dir_fn, set_global_save_dir_fn

    target = tmp_path / "bm" / "shinychat-conversations"

    def save_dir(id: str) -> Path:
        # Another session won the race after our restore attempt failed.
        target.mkdir(parents=True)
        raise RuntimeError(f"Directory {target} already exists")

    def restore_dir(id: str) -> Path:
        if not target.exists():
            raise RuntimeError(f"Directory {target} does not exist.")
        return target

    set_global_save_dir_fn(save_dir)
    set_global_restore_dir_fn(restore_dir)

    assert await resolve_history_dir() == target


@pytest.mark.anyio
async def test_falls_back_locally_when_host_disables_bookmarking(
    caplog: pytest.LogCaptureFixture,
):
    from shiny.bookmark import set_global_restore_dir_fn, set_global_save_dir_fn

    def not_configured(id: str) -> Path:
        raise NotImplementedError(
            "This server is not configured for saving sessions to disk."
        )

    set_global_save_dir_fn(not_configured)
    set_global_restore_dir_fn(not_configured)

    with caplog.at_level(logging.WARNING, logger="shinychat"):
        assert (
            await resolve_history_dir() == Path(".shinychat") / "conversations"
        )

    assert "not configured for saving sessions" in caplog.text


@pytest.mark.anyio
async def test_env_var_beats_bookmark_machinery(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    from shiny.bookmark import set_global_save_dir_fn

    set_global_save_dir_fn(lambda bm_id: tmp_path / "bm" / bm_id)
    monkeypatch.setenv("CONNECT_CONTENT_DATA_DIR", str(tmp_path / "env"))
    assert (
        await resolve_history_dir()
        == tmp_path / "env" / "shinychat-conversations"
    )


@pytest.mark.anyio
async def test_local_fallback():
    assert await resolve_history_dir() == Path(".shinychat") / "conversations"


@pytest.mark.anyio
async def test_falls_back_when_private_api_missing(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.delattr(bookmark_global, "get_bookmark_save_dir_fn")
    assert await resolve_history_dir() == Path(".shinychat") / "conversations"
