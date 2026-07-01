# HistoryController's session-coupled behavior (switch_to, on_response, etc.)
# is covered by Playwright e2e tests (Task 13). This file tests the pure
# helpers that HistoryController delegates to.

import warnings
from datetime import timedelta
from typing import Any
from unittest.mock import AsyncMock

import pytest
from shinychat._history import (
    HistoryController,
    do_bookmark_with_cleanup,
    extend_record_linear,
)
from shinychat._history_store import InMemoryConversationStore
from shinychat._history_types import new_conversation_record


def msg(role: str) -> dict[str, object]:
    return {
        "role": role,
        "segments": [{"content": role, "content_type": "markdown"}],
    }


def test_extend_appends_only_new_groups_with_ui_by_role():
    rec = new_conversation_record(title="t")
    groups = [
        [{"role": "user", "content": "q1"}],
        [{"role": "assistant", "content": "a1"}],
    ]
    extend_record_linear(
        rec, groups, [msg("user"), msg("assistant")], ui_offset=0
    )
    assert len(rec.nodes) == 2
    path = rec.path_node_ids()
    assert rec.nodes[path[0]].turns == [{"role": "user", "content": "q1"}]
    assert rec.nodes[path[0]].ui == [msg("user")]
    assert rec.nodes[path[1]].ui == [msg("assistant")]

    groups += [
        [{"role": "user", "content": "q2"}],
        [{"role": "assistant", "content": "a2"}],
    ]
    all_msgs = [msg("user"), msg("assistant"), msg("user"), msg("assistant")]
    extend_record_linear(rec, groups, all_msgs, ui_offset=2)
    assert len(rec.nodes) == 4
    assert rec.nodes[rec.path_node_ids()[2]].ui == [msg("user")]


def test_extend_groups_tool_exchange_into_single_node():
    user_turn = {
        "role": "user",
        "contents": [{"content_type": "text", "text": "weather?"}],
    }
    asst_req = {
        "role": "assistant",
        "contents": [
            {
                "content_type": "tool_request",
                "id": "x",
                "name": "get_weather",
                "arguments": {},
            }
        ],
    }
    user_res = {
        "role": "user",
        "contents": [
            {"content_type": "tool_result", "id": "x", "value": "Sunny"}
        ],
    }
    asst_final = {
        "role": "assistant",
        "contents": [{"content_type": "text", "text": "It's sunny."}],
    }

    groups = [
        [user_turn],
        [asst_req, user_res, asst_final],
    ]
    msgs = [msg("user"), msg("assistant")]
    rec = new_conversation_record(title="t")
    extend_record_linear(rec, groups, msgs, ui_offset=0)

    assert len(rec.nodes) == 2
    path = rec.path_node_ids()

    user_node = rec.nodes[path[0]]
    asst_node = rec.nodes[path[1]]

    assert len(user_node.turns) == 1
    assert len(asst_node.turns) == 3
    assert user_node.ui == [msg("user")]
    assert asst_node.ui == [msg("assistant")]

    # path_turns() must flatten back to all 4 original turns
    assert rec.path_turns() == [user_turn, asst_req, user_res, asst_final]


def test_extend_attaches_extra_assistant_msgs_to_last_node():
    rec = new_conversation_record(title="t")
    groups = [
        [{"role": "user", "content": "q"}],
        [{"role": "assistant", "content": "a"}],
    ]
    msgs = [
        msg("user"),
        msg("assistant"),
        msg("assistant"),
    ]
    extend_record_linear(rec, groups, msgs, ui_offset=0)
    path = rec.path_node_ids()
    assert rec.nodes[path[1]].ui == [msg("assistant"), msg("assistant")]


def test_extend_noop_when_no_new_groups():
    rec = new_conversation_record(title="t")
    groups = [[{"role": "user", "content": "q"}]]
    extend_record_linear(rec, groups, [msg("user")], ui_offset=0)
    before = rec.model_dump()
    extend_record_linear(rec, groups, [msg("user")], ui_offset=1)
    assert rec.model_dump() == before


def test_extend_with_no_new_ui_messages_leaves_ui_none():
    rec = new_conversation_record(title="t")
    groups = [
        [{"role": "user", "content": "q"}],
        [{"role": "assistant", "content": "a"}],
    ]
    msgs = [msg("user"), msg("assistant")]
    extend_record_linear(rec, groups, msgs, ui_offset=2)
    assert len(rec.nodes) == 2
    assert all(node.ui is None for node in rec.nodes.values())


# --- _suppress_next_save flag (unit-level, no Shiny session needed) ----------


class _FakeChat:
    def _messages_for_bookmark(self) -> list[Any]:
        return []

    async def _send_action(self, action: Any) -> None:
        pass

    async def clear_messages(self) -> None:
        pass

    async def _restore_bookmark_message(self, message_dict: Any) -> None:
        pass


class _FakeAdapter:
    def get_turns_json(self) -> list[Any]:
        return [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi there"},
        ]

    def get_turns_grouped(self) -> list[list[Any]]:
        return [[t] for t in self.get_turns_json()]

    def set_turns_json(self, turns: list[Any]) -> None:
        pass

    def client_info(self) -> dict[str, Any]:
        return {}


class _RecordingStore:
    def __init__(self) -> None:
        self.put_calls: list[tuple[str, Any]] = []

    async def put(self, scope: str, record: Any) -> None:
        self.put_calls.append((scope, record))

    async def list(self, scope: str) -> list[Any]:
        return []


class _FailingStore(_RecordingStore):
    async def put(self, scope: str, record: Any) -> None:
        raise OSError("disk full")


def _make_controller() -> tuple[HistoryController, _RecordingStore]:
    store = _RecordingStore()
    controller = HistoryController(
        chat=_FakeChat(),  # type: ignore[arg-type]
        adapter=_FakeAdapter(),  # type: ignore[arg-type]
        store=store,  # type: ignore[arg-type]
        title_fn=None,
        title_enabled=False,
        client=None,
    )
    controller.scope = "test-scope"
    return controller, store


@pytest.mark.anyio
async def test_suppress_next_save_skips_first_on_response_and_clears():
    controller, store = _make_controller()
    controller._suppress_next_save = True

    await controller.on_response()

    assert store.put_calls == [], "store.put must not be called when suppressed"
    assert controller._suppress_next_save is False, (
        "flag must be cleared after skip"
    )


@pytest.mark.anyio
async def test_suppress_next_save_false_allows_on_response():
    controller, store = _make_controller()
    assert controller._suppress_next_save is False

    # on_response with no turns/messages should still call store.put
    await controller.on_response()

    assert len(store.put_calls) == 1, (
        "store.put should be called when not suppressed"
    )


@pytest.mark.anyio
async def test_second_on_response_after_suppress_proceeds():
    controller, store = _make_controller()
    controller._suppress_next_save = True

    await controller.on_response()  # skipped, flag cleared
    await controller.on_response()  # must proceed

    assert len(store.put_calls) == 1, "second call must reach store.put"


@pytest.mark.anyio
async def test_on_response_no_new_data_does_not_overwrite_saved_values():
    controller, store = _make_controller()
    accent = "info"

    controller._save_callbacks.append(
        lambda values: values.update({"accent": accent})
    )

    await controller.on_response()
    assert controller.record is not None
    assert controller.record.values["accent"] == "info"

    accent = "danger"
    await controller.on_response()

    assert len(store.put_calls) == 1, "no-op flush should not persist again"
    assert controller.record.values["accent"] == "info"


@pytest.mark.anyio
async def test_is_replaying_suppresses_on_response_without_consuming_suppress_flag():
    # Fires during replay must not consume _suppress_next_save so the
    # post-replay flush is still handled correctly.
    controller, store = _make_controller()
    controller._is_replaying = True
    controller._suppress_next_save = True

    await controller.on_response()  # in-flight during replay — skipped

    assert store.put_calls == [], "store.put must not be called while replaying"
    assert controller._suppress_next_save is True, (
        "_suppress_next_save must not be consumed while _is_replaying is True"
    )


@pytest.mark.anyio
async def test_full_replay_sequence_suppresses_then_resumes():
    # Simulates M in-flight fires during replay, one post-replay flush,
    # then a real response — only the real response must be saved.
    controller, store = _make_controller()
    controller._is_replaying = True
    controller._suppress_next_save = True

    # In-flight fires during replay (any number)
    for _ in range(3):
        await controller.on_response()

    assert store.put_calls == [], "no saves during replay"
    assert controller._suppress_next_save is True

    # Replay ends
    controller._is_replaying = False

    # Post-replay flush — consumed by _suppress_next_save
    await controller.on_response()
    assert store.put_calls == [], "post-replay flush must still be suppressed"
    assert controller._suppress_next_save is False

    # Real response after user interaction
    await controller.on_response()
    assert len(store.put_calls) == 1, "real response must be saved"


# --- ui_offset atomicity (not advanced when store.put raises) ----------------


def _make_failing_controller() -> HistoryController:
    store = _FailingStore()
    controller = HistoryController(
        chat=_FakeChat(),  # type: ignore[arg-type]
        adapter=_FakeAdapter(),  # type: ignore[arg-type]
        store=store,  # type: ignore[arg-type]
        title_fn=None,
        title_enabled=False,
        client=None,
    )
    controller.scope = "test-scope"
    return controller


@pytest.mark.anyio
async def test_ui_offset_unchanged_when_on_response_store_put_raises():
    controller = _make_failing_controller()
    initial_offset = controller.ui_offset

    with pytest.raises(OSError):
        await controller.on_response()

    assert controller.ui_offset == initial_offset, (
        "ui_offset must not advance when store.put() raises"
    )


@pytest.mark.anyio
async def test_ui_offset_unchanged_when_save_current_store_put_raises():
    controller = _make_failing_controller()
    controller.record = new_conversation_record(title="t")
    initial_offset = controller.ui_offset

    with pytest.raises(OSError):
        await controller.save_current()

    assert controller.ui_offset == initial_offset, (
        "ui_offset must not advance when store.put() raises"
    )


# --- on_url_change (URL-mode navigation) ------------------------------------


class _NavFakeChat(_FakeChat):
    def __init__(self) -> None:
        self.actions: list[dict[str, Any]] = []
        self.cleared = 0

    async def _send_action(self, action: Any) -> None:
        self.actions.append(dict(action))

    async def clear_messages(self) -> None:
        self.cleared += 1

    async def _restore_bookmark_message(self, message_dict: Any) -> None:
        pass


class _NavFakeAdapter(_FakeAdapter):
    def __init__(self) -> None:
        self.set_calls: list[list[Any]] = []

    def set_turns_json(self, turns: list[Any]) -> None:
        self.set_calls.append(turns)


class _NavStore(_RecordingStore):
    def __init__(self) -> None:
        super().__init__()
        self.records: dict[str, Any] = {}
        self.deleted: list[str] = []

    async def get(self, scope: str, conv_id: str) -> Any:
        return self.records.get(conv_id)

    async def delete(self, scope: str, conv_id: str) -> None:
        self.deleted.append(conv_id)
        self.records.pop(conv_id, None)


def _make_nav_controller(
    *, with_url_mode: bool = False
) -> tuple[HistoryController, _NavStore, _NavFakeChat]:
    store = _NavStore()
    chat = _NavFakeChat()
    controller = HistoryController(
        chat=chat,  # type: ignore[arg-type]
        adapter=_NavFakeAdapter(),  # type: ignore[arg-type]
        store=store,  # type: ignore[arg-type]
        title_fn=None,
        title_enabled=False,
        client=None,
    )
    controller.scope = "test-scope"
    if with_url_mode:

        async def _update_url(conv_id: str | None) -> None:
            url = f"?conv={conv_id}" if conv_id is not None else None
            await controller.send_navigate(url, conv_id)

        controller.on_active_id_change = _update_url
    return controller, store, chat


def _nav_actions(chat: _NavFakeChat) -> list[dict[str, Any]]:
    return [a for a in chat.actions if a["type"] == "history_navigate"]


@pytest.mark.anyio
async def test_switch_to_swaps_in_session():
    controller, store, chat = _make_nav_controller()
    target = new_conversation_record(title="other")
    store.records[target.id] = target

    await controller.switch_to(target.id)

    assert _nav_actions(chat) == []
    assert chat.cleared == 1
    assert controller.record is target


@pytest.mark.anyio
async def test_switch_to_url_mode_sends_navigate():
    controller, store, chat = _make_nav_controller(with_url_mode=True)
    target = new_conversation_record(title="other")
    store.records[target.id] = target

    await controller.switch_to(target.id)

    navs = _nav_actions(chat)
    assert len(navs) == 1
    assert navs[0]["url"] == f"?conv={target.id}"
    assert navs[0]["active_id"] == target.id
    assert chat.cleared == 1
    assert controller.record is target


@pytest.mark.anyio
async def test_new_chat_url_mode_sends_navigate_null():
    controller, _store, chat = _make_nav_controller(with_url_mode=True)

    await controller.new_chat()

    navs = _nav_actions(chat)
    assert navs == [
        {"type": "history_navigate", "url": None, "active_id": None}
    ]
    assert chat.cleared == 1


@pytest.mark.anyio
async def test_send_navigate_can_request_hard_reload():
    controller, _store, chat = _make_nav_controller()

    await controller.send_navigate("?_state_id_=abc123", "c123", reload=True)

    navs = _nav_actions(chat)
    assert navs == [
        {
            "type": "history_navigate",
            "url": "?_state_id_=abc123",
            "active_id": "c123",
            "reload": True,
        }
    ]


@pytest.mark.anyio
async def test_new_chat_browser_mode_no_navigate():
    controller, _store, chat = _make_nav_controller()

    await controller.new_chat()

    assert _nav_actions(chat) == []
    assert chat.cleared == 1


@pytest.mark.anyio
async def test_delete_active_url_mode_sends_navigate_null():
    controller, store, chat = _make_nav_controller(with_url_mode=True)
    active = new_conversation_record(title="doomed")
    store.records[active.id] = active
    controller.record = active

    await controller.delete(active.id)

    assert store.deleted == [active.id]
    navs = _nav_actions(chat)
    assert navs == [
        {"type": "history_navigate", "url": None, "active_id": None}
    ]


@pytest.mark.anyio
async def test_delete_inactive_does_not_navigate():
    controller, store, chat = _make_nav_controller(with_url_mode=True)
    other = new_conversation_record(title="other")
    store.records[other.id] = other

    await controller.delete(other.id)

    assert store.deleted == [other.id]
    assert _nav_actions(chat) == []


@pytest.mark.anyio
async def test_on_response_first_save_url_mode_sends_navigate():
    controller, _store, chat = _make_nav_controller(with_url_mode=True)

    await controller.on_response()

    assert controller.record is not None
    navs = _nav_actions(chat)
    assert len(navs) == 1
    assert navs[0]["url"] == f"?conv={controller.record.id}"


# --- retitle ------------------------------------------------------------------


def _make_retitle_controller(
    title_fn: Any = None,
    raw_client: Any = None,
) -> tuple[HistoryController, _RecordingStore]:
    store = _RecordingStore()
    controller = HistoryController(
        chat=_FakeChat(),  # type: ignore[arg-type]
        adapter=_FakeAdapter(),  # type: ignore[arg-type]
        store=store,  # type: ignore[arg-type]
        title_fn=title_fn,
        title_enabled=True,
        client=raw_client,
    )
    controller.scope = "test-scope"
    return controller, store


@pytest.mark.anyio
async def test_retitle_updates_title_and_persists():
    controller, store = _make_retitle_controller(
        title_fn=lambda turns: "Generated Title",
    )
    controller.record = new_conversation_record(title="fallback")

    await controller.retitle([{"role": "user", "content": "hi"}])

    assert controller.record.title == "Generated Title"
    assert controller.record.title_source == "llm"
    assert len(store.put_calls) == 1


@pytest.mark.anyio
async def test_retitle_noop_when_record_is_none():
    controller, store = _make_retitle_controller(
        title_fn=lambda turns: "should not be used",
    )

    await controller.retitle([])

    assert store.put_calls == []


# --- bookmark callback cleanup ------------------------------------------------


class _BookmarkStub:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.cancel_calls = 0
        self.on_bookmarked_calls = 0

    def on_bookmarked(self, fn: Any) -> Any:
        self.on_bookmarked_calls += 1

        def cancel() -> None:
            self.cancel_calls += 1

        return cancel

    async def do_bookmark(self) -> None:
        if self.fail:
            raise RuntimeError("bookmark failed")


@pytest.mark.anyio
async def test_do_bookmark_with_cleanup_cancels_on_success():
    bookmark = _BookmarkStub()

    async def _on_bookmarked(url: str) -> None:
        pass

    await do_bookmark_with_cleanup(bookmark, _on_bookmarked)

    assert bookmark.on_bookmarked_calls == 1
    assert bookmark.cancel_calls == 1


@pytest.mark.anyio
async def test_do_bookmark_with_cleanup_cancels_on_failure():
    bookmark = _BookmarkStub(fail=True)

    async def _on_bookmarked(url: str) -> None:
        pass

    with pytest.raises(RuntimeError, match="bookmark failed"):
        await do_bookmark_with_cleanup(bookmark, _on_bookmarked)

    assert bookmark.on_bookmarked_calls == 1
    assert bookmark.cancel_calls == 1


@pytest.mark.anyio
async def test_retitle_noop_when_user_already_renamed():
    controller, store = _make_retitle_controller(
        title_fn=lambda turns: "should not be used",
    )
    controller.record = new_conversation_record(title="My Title")
    controller.record.title_source = "user"

    await controller.retitle([])

    assert controller.record.title == "My Title"
    assert store.put_calls == []


@pytest.mark.anyio
async def test_retitle_noop_when_generate_returns_none():
    controller, store = _make_retitle_controller(
        title_fn=lambda turns: None,
    )
    controller.record = new_conversation_record(title="fallback")

    await controller.retitle([])

    assert controller.record.title == "fallback"
    assert controller.record.title_source is None
    assert store.put_calls == []


@pytest.mark.anyio
async def test_retitle_noop_when_conversation_switched_during_generation():
    original = new_conversation_record(title="original")
    replacement = new_conversation_record(title="replacement")

    controller, store = _make_retitle_controller()

    async def slow_title(turns: Any) -> str:
        # Simulate the conversation switching while the LLM call is in flight
        controller.record = replacement
        return "Title for original"

    controller.title_fn = slow_title
    controller.record = original

    await controller.retitle([])

    assert original.title == "original", "must not update the old record"
    assert controller.record is replacement
    assert store.put_calls == []


@pytest.mark.anyio
async def test_retitle_noop_when_user_renames_during_generation():
    record = new_conversation_record(title="fallback")

    controller, store = _make_retitle_controller()

    async def slow_title(turns: Any) -> str:
        # Simulate the user renaming while the LLM call is in flight
        record.title_source = "user"
        record.title = "User's Title"
        return "LLM Title"

    controller.title_fn = slow_title
    controller.record = record

    await controller.retitle([])

    assert record.title == "User's Title"
    assert record.title_source == "user"
    assert store.put_calls == []


# --- deferred titling trigger --------------------------------------------------


class _GrowingFakeAdapter:
    """Like _FakeAdapter, but turns grow across calls to simulate multiple
    real responses (_FakeAdapter always returns the same fixed 2 turns)."""

    def __init__(self) -> None:
        self.turns: list[dict[str, Any]] = []

    def get_turns_json(self) -> list[Any]:
        return list(self.turns)

    def get_turns_grouped(self) -> list[list[Any]]:
        return [[t] for t in self.turns]

    def set_turns_json(self, turns: list[Any]) -> None:
        self.turns = list(turns)

    def client_info(self) -> dict[str, Any]:
        return {}


def _make_deferred_title_controller(
    title_fn: Any = None,
) -> tuple[HistoryController, _RecordingStore, _GrowingFakeAdapter]:
    store = _RecordingStore()
    adapter = _GrowingFakeAdapter()
    controller = HistoryController(
        chat=_FakeChat(),  # type: ignore[arg-type]
        adapter=adapter,  # type: ignore[arg-type]
        store=store,  # type: ignore[arg-type]
        title_fn=title_fn,
        title_enabled=True,
        client=None,
    )
    controller.scope = "test-scope"
    return controller, store, adapter


@pytest.mark.anyio
async def test_title_stays_fallback_after_first_response():
    controller, _store, adapter = _make_deferred_title_controller(
        title_fn=lambda turns: "Generated Title",
    )
    adapter.turns = [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
    ]

    await controller.on_response()

    assert controller.record is not None
    assert controller.record.response_count == 1
    assert controller.record.title_source is None
    assert controller._title_task is None


@pytest.mark.anyio
async def test_titling_fires_after_second_response_exactly_once():
    controller, _store, adapter = _make_deferred_title_controller(
        title_fn=lambda turns: "Generated Title",
    )
    adapter.turns = [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
    ]
    await controller.on_response()
    task_after_first_response = controller._title_task
    assert task_after_first_response is None

    adapter.turns += [
        {"role": "user", "content": "more"},
        {"role": "assistant", "content": "sure"},
    ]
    await controller.on_response()

    assert controller.record is not None
    assert controller.record.response_count == 2
    title_task = controller._title_task
    assert title_task is not None
    await title_task
    assert controller.record.title == "Generated Title"
    assert controller.record.title_source == "llm"


@pytest.mark.anyio
async def test_rename_between_first_and_second_response_blocks_auto_titling():
    controller, _store, adapter = _make_deferred_title_controller(
        title_fn=lambda turns: "Generated Title",
    )
    adapter.turns = [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
    ]
    await controller.on_response()
    assert controller.record is not None
    await controller.rename(controller.record.id, "My Title")

    adapter.turns += [
        {"role": "user", "content": "more"},
        {"role": "assistant", "content": "sure"},
    ]
    await controller.on_response()

    assert controller.record is not None
    assert controller._title_task is None
    assert controller.record.title == "My Title"
    assert controller.record.title_source == "user"


@pytest.mark.anyio
async def test_titling_fires_on_second_response_across_sessions():
    store = InMemoryConversationStore()
    adapter1 = _GrowingFakeAdapter()
    controller1 = HistoryController(
        chat=_FakeChat(),  # type: ignore[arg-type]
        adapter=adapter1,  # type: ignore[arg-type]
        store=store,
        title_fn=lambda turns: "Generated Title",
        title_enabled=True,
        client=None,
    )
    controller1.scope = "test-scope"
    adapter1.turns = [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
    ]
    await controller1.on_response()
    assert controller1.record is not None
    conv_id = controller1.record.id
    assert controller1._title_task is None

    # Simulate a brand-new session: fresh controller, same backing store,
    # loads the persisted (1-response) conversation before continuing it.
    adapter2 = _GrowingFakeAdapter()
    adapter2.turns = list(adapter1.turns)
    controller2 = HistoryController(
        chat=_FakeChat(),  # type: ignore[arg-type]
        adapter=adapter2,  # type: ignore[arg-type]
        store=store,
        title_fn=lambda turns: "Generated Title",
        title_enabled=True,
        client=None,
    )
    controller2.scope = "test-scope"
    controller2.record = await store.get("test-scope", conv_id)

    adapter2.turns += [
        {"role": "user", "content": "more"},
        {"role": "assistant", "content": "sure"},
    ]
    await controller2.on_response()

    title_task = controller2._title_task
    assert title_task is not None
    await title_task
    assert controller2.record is not None
    assert controller2.record.title == "Generated Title"
    assert controller2.record.title_source == "llm"


# --- save/restore callbacks --------------------------------------------------


def _make_fake_chat() -> _FakeChat:
    return _FakeChat()


@pytest.mark.anyio
async def test_save_callback_fires_and_values_stored(tmp_path: Any) -> None:
    """on_save callback populates record.values."""
    from shinychat._history_store import FileConversationStore

    save_calls: list[dict[str, Any]] = []
    save_cbs: list[Any] = []

    def my_save(values: dict[str, Any]) -> None:
        values["x"] = 42
        save_calls.append(dict(values))

    save_cbs.append(my_save)

    store = FileConversationStore(tmp_path)
    adapter = _FakeAdapter()
    controller = HistoryController(
        chat=_make_fake_chat(),  # type: ignore[arg-type]
        adapter=adapter,  # type: ignore[arg-type]
        store=store,
        title_fn=None,
        title_enabled=False,
        client=object(),
        save_callbacks=save_cbs,
        restore_callbacks=[],
    )
    controller.scope = "alice"

    await controller.on_response()

    assert len(save_calls) == 1
    assert save_calls[0]["x"] == 42
    assert controller.record is not None
    assert controller.record.values.get("x") == 42


@pytest.mark.anyio
async def test_restore_callback_fires_on_switch(tmp_path: Any) -> None:
    """on_restore callback receives stored values on switch_to."""
    from shinychat._history_store import FileConversationStore
    from shinychat._history_types import new_conversation_record

    restored: list[dict[str, Any]] = []
    restore_cbs: list[Any] = [lambda v: restored.append(dict(v))]

    store = FileConversationStore(tmp_path)
    adapter = _NavFakeAdapter()
    chat = _NavFakeChat()
    controller = HistoryController(
        chat=chat,  # type: ignore[arg-type]
        adapter=adapter,  # type: ignore[arg-type]
        store=store,
        title_fn=None,
        title_enabled=False,
        client=object(),
        save_callbacks=[],
        restore_callbacks=restore_cbs,
    )
    controller.scope = "alice"

    # Create a record with values directly in the store (not via on_response,
    # which would immediately re-capture and overwrite our values).
    target = new_conversation_record(title="old")
    target.values = {"x": 99}
    await store.put("alice", target)

    # Simulate having a different current conversation
    other = new_conversation_record(title="current")
    await store.put("alice", other)
    controller.record = other

    await controller.switch_to(target.id)

    assert any(r.get("x") == 99 for r in restored)


# ---------------------------------------------------------------------------
# _evict_if_needed
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_evict_if_needed_noop_when_no_limit():
    store = InMemoryConversationStore()
    rec = new_conversation_record(title="t")
    await store.put("alice", rec)

    controller = HistoryController(
        chat=_FakeChat(),  # type: ignore[arg-type]
        adapter=_FakeAdapter(),  # type: ignore[arg-type]
        store=store,
        title_fn=None,
        title_enabled=False,
        client=None,
        max_store_bytes=None,
    )
    controller.scope = "alice"

    await controller._evict_if_needed()
    assert len(await store.list("alice")) == 1


@pytest.mark.anyio
async def test_evict_if_needed_noop_when_under_limit():
    store = InMemoryConversationStore()
    rec = new_conversation_record(title="t")
    await store.put("alice", rec)

    controller = HistoryController(
        chat=_FakeChat(),  # type: ignore[arg-type]
        adapter=_FakeAdapter(),  # type: ignore[arg-type]
        store=store,
        title_fn=None,
        title_enabled=False,
        client=None,
        max_store_bytes=100
        * 1024
        * 1024,  # 100 MB — well above any test record
    )
    controller.scope = "alice"

    await controller._evict_if_needed()
    assert len(await store.list("alice")) == 1


@pytest.mark.anyio
async def test_evict_if_needed_removes_oldest_preserves_active():
    store = InMemoryConversationStore()

    rec1 = new_conversation_record(title="oldest")
    rec2 = new_conversation_record(title="middle")
    rec3 = new_conversation_record(title="newest")
    rec2.updated_at = rec2.updated_at + timedelta(seconds=1)
    rec3.updated_at = rec3.updated_at + timedelta(seconds=2)
    for rec in [rec1, rec2, rec3]:
        await store.put("alice", rec)

    controller = HistoryController(
        chat=_FakeChat(),  # type: ignore[arg-type]
        adapter=_FakeAdapter(),  # type: ignore[arg-type]
        store=store,
        title_fn=None,
        title_enabled=False,
        client=None,
        max_store_bytes=1,  # 1 byte: ensures all non-active records are evicted
    )
    controller.scope = "alice"
    controller.record = rec3  # newest is active

    await controller._evict_if_needed()

    remaining = {m.id for m in await store.list("alice")}
    assert rec1.id not in remaining
    assert rec2.id not in remaining
    assert rec3.id in remaining


@pytest.mark.anyio
async def test_evict_if_needed_calls_list_once_and_never_total_size():
    # Regression: total_size() used to be re-called (a full-scope sweep) on
    # every eviction iteration. The running total should now come entirely
    # from a single list() call's per-record size_bytes.
    store = InMemoryConversationStore()
    rec1 = new_conversation_record(title="oldest")
    rec2 = new_conversation_record(title="middle")
    rec3 = new_conversation_record(title="newest")
    rec2.updated_at = rec2.updated_at + timedelta(seconds=1)
    rec3.updated_at = rec3.updated_at + timedelta(seconds=2)
    for rec in [rec1, rec2, rec3]:
        await store.put("alice", rec)

    controller = HistoryController(
        chat=_FakeChat(),  # type: ignore[arg-type]
        adapter=_FakeAdapter(),  # type: ignore[arg-type]
        store=store,
        title_fn=None,
        title_enabled=False,
        client=None,
        max_store_bytes=1,
    )
    controller.scope = "alice"
    controller.record = rec3

    list_spy = AsyncMock(wraps=store.list)
    total_size_spy = AsyncMock(wraps=store.total_size)
    store.list = list_spy  # type: ignore[method-assign]
    store.total_size = total_size_spy  # type: ignore[method-assign]

    await controller._evict_if_needed()

    assert list_spy.call_count == 1
    assert total_size_spy.call_count == 0


@pytest.mark.anyio
async def test_evict_if_needed_warns_once_when_active_alone_exceeds_budget():
    store = InMemoryConversationStore()
    rec = new_conversation_record(title="big")
    rec.append_linear([{"role": "user", "content": "x" * 1000}])
    await store.put("alice", rec)

    controller = HistoryController(
        chat=_FakeChat(),  # type: ignore[arg-type]
        adapter=_FakeAdapter(),  # type: ignore[arg-type]
        store=store,
        title_fn=None,
        title_enabled=False,
        client=None,
        max_store_bytes=1,
    )
    controller.scope = "alice"
    controller.record = rec  # active; nothing else to evict

    with pytest.warns(UserWarning, match="remains over"):
        await controller._evict_if_needed()

    with warnings.catch_warnings():
        warnings.simplefilter("error")
        await controller._evict_if_needed()  # must not warn a second time


@pytest.mark.anyio
async def test_evict_one_deletes_from_store():
    store = InMemoryConversationStore()
    rec = new_conversation_record(title="old")
    await store.put("alice", rec)

    controller = HistoryController(
        chat=_FakeChat(),  # type: ignore[arg-type]
        adapter=_FakeAdapter(),  # type: ignore[arg-type]
        store=store,
        title_fn=None,
        title_enabled=False,
        client=None,
        max_store_bytes=None,
    )
    controller.scope = "alice"

    await controller._evict_one(rec.id)

    assert await store.get("alice", rec.id) is None


# ---------------------------------------------------------------------------
# Controller lifecycle hooks: on_response_saved, on_pre_switch, on_evict
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_on_response_saved_fires_when_new_data_is_saved():
    controller, store = _make_controller()
    fired: list[str] = []
    turns = [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hi there"},
    ]

    class _GrowingAdapter(_FakeAdapter):
        def get_turns_json(self) -> list[Any]:
            return turns

    async def hook(record: Any) -> None:
        fired.append(record.id)

    controller.adapter = _GrowingAdapter()  # type: ignore[assignment]
    controller.on_response_saved = hook

    await controller.on_response()
    turns.extend(
        [
            {"role": "user", "content": "more"},
            {"role": "assistant", "content": "sure"},
        ]
    )
    await controller.on_response()

    assert len(fired) == 2
    assert fired[0] == fired[1]  # same conversation id both times


@pytest.mark.anyio
async def test_on_response_saved_not_fired_when_suppressed():
    controller, store = _make_controller()
    fired: list[str] = []

    async def hook(record: Any) -> None:
        fired.append(record.id)

    controller.on_response_saved = hook
    controller._suppress_next_save = True

    await controller.on_response()  # suppressed

    assert fired == []


@pytest.mark.anyio
async def test_on_pre_switch_true_skips_in_session_swap():
    controller, store, chat = _make_nav_controller()
    target = new_conversation_record(title="other")
    store.records[target.id] = target
    pre_switch_calls: list[str] = []

    async def hook(rec: Any) -> bool:
        pre_switch_calls.append(rec.id)
        return True  # signal: skip in-session swap

    controller.on_pre_switch = hook

    await controller.switch_to(target.id)

    assert pre_switch_calls == [target.id]
    # In-session swap was skipped: client turns NOT updated, UI NOT cleared
    assert chat.cleared == 0
    # record not changed because we returned True (navigation handled by hook)
    assert controller.record is None


@pytest.mark.anyio
async def test_on_pre_switch_false_allows_in_session_swap():
    controller, store, chat = _make_nav_controller()
    target = new_conversation_record(title="other")
    store.records[target.id] = target
    pre_switch_calls: list[str] = []

    async def hook(rec: Any) -> bool:
        pre_switch_calls.append(rec.id)
        return False  # allow normal in-session swap

    controller.on_pre_switch = hook

    await controller.switch_to(target.id)

    assert pre_switch_calls == [target.id]
    assert chat.cleared == 1
    assert controller.record is target


# --- on_evict hook -----------------------------------------------------------


@pytest.mark.anyio
async def test_on_evict_fires_before_store_delete_in_evict_one():
    store = InMemoryConversationStore()
    rec = new_conversation_record(title="old")
    await store.put("alice", rec)

    order: list[str] = []

    controller = HistoryController(
        chat=_FakeChat(),  # type: ignore[arg-type]
        adapter=_FakeAdapter(),  # type: ignore[arg-type]
        store=store,
        title_fn=None,
        title_enabled=False,
        client=None,
    )
    controller.scope = "alice"

    async def hook(conv_id: str) -> None:
        # Record must still exist in store when the hook fires
        still_there = await store.get("alice", conv_id)
        order.append("hook_before" if still_there is not None else "hook_after")

    controller.on_evict = hook

    await controller._evict_one(rec.id)

    assert order == ["hook_before"]
    assert await store.get("alice", rec.id) is None


@pytest.mark.anyio
async def test_on_evict_fires_before_store_delete_in_delete():
    store = InMemoryConversationStore()
    rec = new_conversation_record(title="old")
    await store.put("alice", rec)

    order: list[str] = []

    controller = HistoryController(
        chat=_NavFakeChat(),  # type: ignore[arg-type]
        adapter=_NavFakeAdapter(),  # type: ignore[arg-type]
        store=store,
        title_fn=None,
        title_enabled=False,
        client=None,
    )
    controller.scope = "alice"

    async def hook(conv_id: str) -> None:
        still_there = await store.get("alice", conv_id)
        order.append("hook_before" if still_there is not None else "hook_after")

    controller.on_evict = hook

    await controller.delete(rec.id)

    assert order == ["hook_before"]
    assert await store.get("alice", rec.id) is None
