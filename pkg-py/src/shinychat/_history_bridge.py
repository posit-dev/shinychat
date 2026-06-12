from __future__ import annotations

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
