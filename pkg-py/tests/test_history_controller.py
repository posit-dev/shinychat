# HistoryController's session-coupled behavior (switch_to, on_response, etc.)
# is covered by Playwright e2e tests (Task 13). This file tests the pure
# helpers that HistoryController delegates to.

import asyncio
from typing import Any

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
