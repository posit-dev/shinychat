from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import TYPE_CHECKING

from shiny import reactive

# local_restore_dir and get_bookmark_restore_dir_fn have no public equivalent.
# TODO: replace delete_state() internals with session.bookmark.delete_state()
# once Shiny exposes a public API for removing server bookmark state dirs.
# Also tracked: eviction in FileConversationStore bypasses the controller, so
# bookmark files for evicted conversations are not cleaned up. Python's store
# has no max_conversations limit at all — eviction policy should be made
# consistent between R and Python before this becomes a real problem.
from shiny.bookmark._bookmark_state import local_restore_dir
from shiny.bookmark._global import get_bookmark_restore_dir_fn

from ._history_store import CONV_ID_RE

if TYPE_CHECKING:
    from shiny.session import Session

    from ._history_types import ConversationRecord


class BookmarkMinter:
    """
    Manage server bookmark state for restore_mode="url".

    One bookmark file is minted per conversation on first save via the public
    get_bookmark_url() API. The same state_id is reused for the lifetime of
    the conversation — the URL only changes when switching conversations.
    Bookmark files are cleaned up when a conversation is explicitly deleted.
    """

    def __init__(self, session: "Session"):
        self._root = session.root_scope()

    async def mint_if_needed(self, record: "ConversationRecord") -> None:
        """Mint a bookmark for *record* on first save; no-op if already minted."""
        if record.bookmark_state_id is not None:
            return
        url = await self._root.bookmark.get_bookmark_url()
        if url is None:
            return
        # get_bookmark_url() returns the full URL; parse "_state_id_=<id>" from it.
        m = re.search(r"[?&]_state_id_=([^&]+)", url)
        if m is None:
            return
        state_id = m.group(1)
        record.bookmark_state_id = state_id
        await self._root.bookmark.update_query_string(
            f"?_state_id_={state_id}", mode="replace"
        )

    async def delete_state(self, state_id: str) -> None:
        """Best-effort removal of a previously minted state dir."""
        if not CONV_ID_RE.fullmatch(state_id):
            return
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
            pass

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
