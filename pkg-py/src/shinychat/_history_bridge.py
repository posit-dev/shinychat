from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from shiny import reactive

# This module deliberately concentrates every use of shiny's private
# bookmark internals (BookmarkState/RestoreState construction, the
# _on_bookmark/_on_restore callback registries). Tracked upstream item:
# replace with public shiny hooks.
#
# Note: BookmarkState is in _save_state, not _bookmark (verified against
# installed shiny). Both modules import cleanly at module load with no
# circular-import side-effects, so we use top-level imports per repo style.
from shiny.bookmark._bookmark_state import local_restore_dir
from shiny.bookmark._global import get_bookmark_restore_dir_fn
from shiny.bookmark._restore_state import RestoreState
from shiny.bookmark._save_state import BookmarkState


class BookmarkBridge:
    """
    Drive the session's bookmark save/restore callbacks against
    conversation-history state instead of a real Shiny bookmark.

    Boundary: only the bookmark *values* dict and the on_restore/on_restored
    callbacks are replayed. Raw Shiny input restoration (which a real
    bookmark URL performs client-side) does not happen here.
    """

    def __init__(self, session: Any, exclude_keys: set[str]):
        self._root = session.root_scope()
        self._exclude = set(exclude_keys)

    async def capture(self) -> dict[str, Any]:
        bookmark = self._root.bookmark
        if bookmark._on_bookmark_callbacks.count() == 0:
            return {}

        async def noop_save(_state: Any) -> None:
            pass

        # BookmarkState.__init__(input, exclude, on_save) — positional, not keyword-only.
        # We pass the session's real input object; _on_save is never called because
        # we only read state.values, never call _save_state or _encode_state.
        state = BookmarkState(self._root.input, [], noop_save)
        with reactive.isolate():
            await bookmark._on_bookmark_callbacks.invoke(state)
        return {k: v for k, v in state.values.items() if k not in self._exclude}

    async def restore(self, values: dict[str, Any]) -> None:
        bookmark = self._root.bookmark
        # RestoreState.__init__(*, input, values, dir) — keyword-only.
        # input accepts a plain dict; no RestoreInputSet transformation in __init__.
        state = RestoreState(input={}, values=dict(values), dir=None)
        with reactive.isolate():
            if bookmark._on_restore_callbacks.count() > 0:
                await bookmark._on_restore_callbacks.invoke(state)
            if bookmark._on_restored_callbacks.count() > 0:
                await bookmark._on_restored_callbacks.invoke(state)


class BookmarkMinter:
    """
    Mint real server bookmarks for conversation saves (restore_mode="url").

    Mirrors the body of `session.bookmark.get_bookmark_url()` (store="server"
    branch) rather than calling it: we need the state id *and* the captured
    values dict, which that API does not expose. One `on_bookmark` callback
    pass per mint — this replaces `BookmarkBridge.capture()` in url mode.
    """

    def __init__(self, session: Any, exclude_keys: set[str]):
        self._root = session.root_scope()
        self._exclude = set(exclude_keys)

    async def mint(self) -> tuple[str, dict[str, Any]]:
        """Persist a bookmark state; return (state_id, values minus excludes)."""
        bookmark = self._root.bookmark

        async def on_save(state: Any) -> None:
            await bookmark._on_bookmark_callbacks.invoke(state)

        state = BookmarkState(
            self._root.input, bookmark._get_bookmark_exclude(), on_save
        )
        with reactive.isolate():
            # Returns "_state_id_=<id>"; writes input.json/values.json to the
            # dir resolved by the app/global/local save-dir chain.
            query_string = await state._save_state(app=self._root.app)
        state_id = query_string.split("=", 1)[1]
        values = {
            k: v for k, v in state.values.items() if k not in self._exclude
        }
        return state_id, values

    async def delete_state(self, state_id: str) -> None:
        """Best-effort removal of a previously minted state dir."""
        try:
            fn = get_bookmark_restore_dir_fn(
                self._root.app._bookmark_restore_dir_fn
            )
            if fn is None:
                fn = local_restore_dir
            state_dir = Path(await fn(state_id))
            if state_dir.is_dir():
                shutil.rmtree(state_dir)
        except Exception:
            pass  # orphaned dirs are bounded: one per conversation save

    async def update_query_string(self, state_id: str) -> None:
        await self._root.bookmark.update_query_string(
            f"?_state_id_={state_id}", mode="replace"
        )

    def base_url(self) -> str:
        cd = self._root.clientdata
        with reactive.isolate():
            port = str(cd.url_port())
            return "".join(
                [
                    cd.url_protocol(),
                    "//",
                    cd.url_hostname(),
                    ":" if port else "",
                    port,
                    cd.url_pathname(),
                ]
            )

    def url_with_state(self, state_id: str) -> str:
        return f"{self.base_url()}?_state_id_={state_id}"
