# HistoryController's session-coupled behavior (switch_to, on_response, etc.)
# is covered by Playwright e2e tests (Task 13). This file tests the pure
# helpers that HistoryController delegates to.

import asyncio
from typing import Any

import pytest
from shinychat._history import HistoryController, extend_record_linear
from shinychat._history_types import new_conversation_record


def msg(role: str) -> dict[str, object]:
    return {
        "role": role,
        "segments": [{"content": role, "content_type": "markdown"}],
    }


def test_extend_appends_only_new_turns_with_ui_by_role():
    rec = new_conversation_record(title="t")
    turns = [
        {"role": "user", "content": "q1"},
        {"role": "assistant", "content": "a1"},
    ]
    extend_record_linear(
        rec, turns, [msg("user"), msg("assistant")], ui_offset=0
    )
    assert len(rec.nodes) == 2
    path = rec.path_node_ids()
    assert rec.nodes[path[0]].ui == [msg("user")]
    assert rec.nodes[path[1]].ui == [msg("assistant")]

    turns += [
        {"role": "user", "content": "q2"},
        {"role": "assistant", "content": "a2"},
    ]
    all_msgs = [msg("user"), msg("assistant"), msg("user"), msg("assistant")]
    extend_record_linear(rec, turns, all_msgs, ui_offset=2)
    assert len(rec.nodes) == 4
    assert rec.nodes[rec.path_node_ids()[2]].ui == [msg("user")]


def test_extend_attaches_extra_assistant_msgs_to_last_assistant_node():
    rec = new_conversation_record(title="t")
    turns = [
        {"role": "user", "content": "q"},
        {"role": "assistant", "content": "a"},
    ]
    msgs = [
        msg("user"),
        msg("assistant"),
        msg("assistant"),
    ]  # e.g. tool display
    extend_record_linear(rec, turns, msgs, ui_offset=0)
    path = rec.path_node_ids()
    assert rec.nodes[path[1]].ui == [msg("assistant"), msg("assistant")]


def test_extend_noop_when_no_new_turns():
    rec = new_conversation_record(title="t")
    turns = [{"role": "user", "content": "q"}]
    extend_record_linear(rec, turns, [msg("user")], ui_offset=0)
    before = rec.model_dump()
    extend_record_linear(rec, turns, [msg("user")], ui_offset=1)
    assert rec.model_dump() == before


def test_extend_with_no_new_ui_messages_leaves_ui_none():
    rec = new_conversation_record(title="t")
    turns = [
        {"role": "user", "content": "q"},
        {"role": "assistant", "content": "a"},
    ]
    msgs = [msg("user"), msg("assistant")]
    extend_record_linear(
        rec, turns, msgs, ui_offset=2
    )  # all ui already attached elsewhere
    assert len(rec.nodes) == 2
    assert all(node.ui is None for node in rec.nodes.values())


# --- _suppress_next_save flag (unit-level, no Shiny session needed) ----------


class _FakeChat:
    def _messages_for_bookmark(self) -> list[Any]:
        return []

    async def _send_action(self, action: Any) -> None:
        pass


class _FakeAdapter:
    def get_turns_json(self) -> list[Any]:
        return []

    def client_info(self) -> dict[str, Any]:
        return {}


class _RecordingStore:
    def __init__(self) -> None:
        self.put_calls: list[tuple[str, Any]] = []

    async def put(self, scope: str, record: Any) -> None:
        self.put_calls.append((scope, record))

    async def list(self, scope: str) -> list[Any]:
        return []


def _make_controller() -> tuple[HistoryController, _RecordingStore]:
    store = _RecordingStore()
    controller = HistoryController(
        chat=_FakeChat(),  # type: ignore[arg-type]
        adapter=_FakeAdapter(),  # type: ignore[arg-type]
        store=store,  # type: ignore[arg-type]
        title_fn=None,
        title_enabled=False,
        raw_client=None,
    )
    controller.scope = "test-scope"
    return controller, store


def test_suppress_next_save_skips_first_on_response_and_clears():
    controller, store = _make_controller()
    controller._suppress_next_save = True

    asyncio.run(controller.on_response())

    assert store.put_calls == [], "store.put must not be called when suppressed"
    assert controller._suppress_next_save is False, (
        "flag must be cleared after skip"
    )


def test_suppress_next_save_false_allows_on_response():
    controller, store = _make_controller()
    assert controller._suppress_next_save is False

    # on_response with no turns/messages should still call store.put
    asyncio.run(controller.on_response())

    assert len(store.put_calls) == 1, (
        "store.put should be called when not suppressed"
    )


def test_second_on_response_after_suppress_proceeds():
    controller, store = _make_controller()
    controller._suppress_next_save = True

    asyncio.run(controller.on_response())  # skipped, flag cleared
    asyncio.run(controller.on_response())  # must proceed

    assert len(store.put_calls) == 1, "second call must reach store.put"


# --- minter integration (controller mint-on-save) ---------------------------


class _FakeMinter:
    def __init__(self) -> None:
        self.mint_count = 0
        self.deleted: list[str] = []
        self.query_updates: list[str] = []

    async def mint(self) -> tuple[str, dict[str, Any]]:
        self.mint_count += 1
        return (f"sid{self.mint_count}", {"minted": self.mint_count})

    async def delete_state(self, state_id: str) -> None:
        self.deleted.append(state_id)

    async def update_query_string(self, state_id: str) -> None:
        self.query_updates.append(state_id)

    def base_url(self) -> str:
        return "http://x/app/"

    def url_with_state(self, state_id: str) -> str:
        return f"http://x/app/?_state_id_={state_id}"


def test_on_response_with_minter_sets_state_id_and_values():
    controller, store = _make_controller()
    minter = _FakeMinter()
    controller.minter = minter  # type: ignore[assignment]

    asyncio.run(controller.on_response())

    assert controller.record is not None
    assert controller.record.bookmark_state_id == "sid1"
    assert controller.record.values == {"minted": 1}
    assert minter.deleted == []
    assert minter.query_updates == ["sid1"]
    assert len(store.put_calls) == 1


def test_second_save_deletes_previous_state_id():
    controller, _store = _make_controller()
    minter = _FakeMinter()
    controller.minter = minter  # type: ignore[assignment]

    asyncio.run(controller.on_response())
    asyncio.run(controller.on_response())

    assert controller.record is not None
    assert controller.record.bookmark_state_id == "sid2"
    assert minter.deleted == ["sid1"]
    assert minter.query_updates == ["sid1", "sid2"]


def test_mint_failure_keeps_record_save_and_previous_state_id():
    controller, store = _make_controller()

    class _FailingMinter(_FakeMinter):
        async def mint(self) -> tuple[str, dict[str, Any]]:
            raise RuntimeError("disk full")

    controller.minter = _FailingMinter()  # type: ignore[assignment]

    with pytest.warns(UserWarning, match="Bookmark mint failed"):
        asyncio.run(controller.on_response())

    assert len(store.put_calls) == 1, "save must proceed despite mint failure"
    assert controller.record is not None
    assert controller.record.bookmark_state_id is None


# --- navigation on switch / new chat / delete --------------------------------


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


def _make_nav_controller() -> tuple[
    HistoryController, _NavStore, _NavFakeChat, _FakeMinter
]:
    store = _NavStore()
    chat = _NavFakeChat()
    minter = _FakeMinter()
    controller = HistoryController(
        chat=chat,  # type: ignore[arg-type]
        adapter=_NavFakeAdapter(),  # type: ignore[arg-type]
        store=store,  # type: ignore[arg-type]
        title_fn=None,
        title_enabled=False,
        raw_client=None,
    )
    controller.scope = "test-scope"
    controller.minter = minter  # type: ignore[assignment]
    return controller, store, chat, minter


def _nav_actions(chat: _NavFakeChat) -> list[dict[str, Any]]:
    return [a for a in chat.actions if a["type"] == "history_navigate"]


def test_switch_to_bookmarked_target_navigates_instead_of_replaying():
    controller, store, chat, _minter = _make_nav_controller()
    target = new_conversation_record(title="other")
    target.bookmark_state_id = "sidT"
    store.records[target.id] = target

    asyncio.run(controller.switch_to(target.id))

    navs = _nav_actions(chat)
    assert navs == [
        {
            "type": "history_navigate",
            "url": "http://x/app/?_state_id_=sidT",
            "active_id": target.id,
        }
    ]
    assert chat.cleared == 0, "must not replay in-session before navigating"
    assert controller.record is None, "binding happens in the next session"


def test_switch_to_bookmarkless_target_swaps_in_session():
    controller, store, chat, _minter = _make_nav_controller()
    target = new_conversation_record(title="legacy")
    store.records[target.id] = target

    asyncio.run(controller.switch_to(target.id))

    assert _nav_actions(chat) == []
    assert chat.cleared == 1
    assert controller.record is target


def test_new_chat_with_minter_navigates_to_base_url():
    controller, _store, chat, _minter = _make_nav_controller()

    asyncio.run(controller.new_chat())

    assert _nav_actions(chat) == [
        {"type": "history_navigate", "url": "http://x/app/", "active_id": None}
    ]
    assert chat.cleared == 0


def test_delete_active_with_minter_navigates_to_base_url():
    controller, store, chat, _minter = _make_nav_controller()
    active = new_conversation_record(title="doomed")
    store.records[active.id] = active
    controller.record = active

    asyncio.run(controller.delete(active.id))

    assert store.deleted == [active.id]
    assert _nav_actions(chat) == [
        {"type": "history_navigate", "url": "http://x/app/", "active_id": None}
    ]


def test_delete_inactive_with_minter_does_not_navigate():
    controller, store, chat, _minter = _make_nav_controller()
    other = new_conversation_record(title="other")
    store.records[other.id] = other

    asyncio.run(controller.delete(other.id))

    assert store.deleted == [other.id]
    assert _nav_actions(chat) == []
