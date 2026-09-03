from __future__ import annotations

from typing import Any, cast

from shiny.module import ResolvedId
from shiny.session import session_context
from shinychat import Chat


class _Bookmark:
    def __init__(self) -> None:
        self.exclude: list[str] = []

    def on_bookmark(self, callback: Any) -> Any:
        return callback

    def on_restore(self, callback: Any) -> Any:
        return callback

    def on_bookmarked(self, callback: Any) -> Any:
        return lambda: None


class _Session:
    ns = ResolvedId("")
    app = None
    id = "bookmark-exclusions"

    def __init__(self) -> None:
        self.bookmark = _Bookmark()

    def is_stub_session(self) -> bool:
        return False

    def root_scope(self) -> _Session:
        return self

    def on_ended(self, callback: Any) -> Any:
        return lambda: None

    def on_destroy(self, callback: Any) -> None:
        pass

    def _increment_busy_count(self) -> None:
        pass

    async def send_custom_message(self, type: str, message: Any) -> None:
        pass


class _Client:
    async def get_state(self) -> dict[str, Any]:
        return {}

    async def set_state(self, state: Any) -> None:
        pass


def test_enable_bookmarking_does_not_exclude_messages_input() -> None:
    session = _Session()
    with session_context(cast(Any, session)):
        chat = Chat("bookmark_chat")
        chat.enable_bookmarking(_Client())

    assert "bookmark_chat_messages" not in session.bookmark.exclude
