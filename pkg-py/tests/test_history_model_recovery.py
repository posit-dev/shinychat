"""Compatible model recovery after a read-only history detour."""

from typing import Any, cast
from unittest.mock import patch

import pytest
from _history_test_helpers import replay_exchange_record
from pydantic import JsonValue
from shiny import reactive
from shiny.session import session_context
from shinychat._chat_types import ReadOnlyReason
from shinychat._history_store import InMemoryConversationStore
from shinychat._history_types import (
    TURNS_STATE_KEY,
    VALUES_STATE_KEY,
    StateEntry,
    TurnDict,
)
from test_chat_history import _history_updates
from test_history_controller import (
    _FakeAdapter,
    _FakeChat,
    _make_controller,
    _make_v2_navigation_controller,
    _stored_message,
)
from test_history_node_first import _record_with_browsable_failure
from test_history_node_first_review import _view


def _turns(*texts: str) -> list[dict[str, Any]]:
    return [{"role": "user", "content": text} for text in texts]


@pytest.mark.anyio
async def test_kvte_unavailable_initial_load_recovers_compatible_sibling() -> (
    None
):
    seed, _chat, _adapter, _store, original, unavailable = (
        _make_v2_navigation_controller()
    )
    record = seed._exchange_recorder.record
    assert record is not None
    record.nodes[unavailable].state[TURNS_STATE_KEY].kind = "unsupported"
    record.nodes[original].state[VALUES_STATE_KEY] = StateEntry(
        kind="values", version=1, mode="snapshot", data={"tab": "original"}
    )
    original_outgoing = record.nodes[unavailable].model_dump()["state"]
    controller, store = _make_controller()
    adapter = cast(_FakeAdapter, controller.adapter)
    observations: list[tuple[dict[str, Any], list[dict[str, Any]]]] = []
    controller._restore_callbacks.append(
        lambda values: observations.append((dict(values), list(adapter.turns)))
    )

    with pytest.warns(UserWarning, match="model context is unavailable"):
        await replay_exchange_record(controller, record)
    recorder = controller._exchange_recorder
    assert recorder.record is not None
    assert recorder.record.active_leaf == unavailable
    assert recorder.read_only_reason == "model_unavailable"
    assert not recorder.source_isolated
    assert not recorder.continuation_allowed
    chat = cast(_FakeChat, controller.chat)
    assert [m["segments"][0]["content"] for m in chat.restored_messages] == [
        "first",
        "custom prefix",
        "replacement",
        "replacement reply",
    ]
    adapter.turns = _turns("untrusted live context")
    observations.clear()

    await controller.handle_navigate(2, "prev", request_id="compatible")

    expected = [
        {"role": "system", "content": "bootstrap"},
        {"role": "user", "content": "first"},
        {"role": "user", "content": "original"},
    ]
    assert recorder.record.active_leaf == original
    assert observations == [({"tab": "original"}, expected)]
    assert adapter.turns == expected
    assert (
        recorder.record.nodes[unavailable].model_dump()["state"]
        == original_outgoing
    )
    assert not recorder.read_only
    assert recorder.continuation_allowed
    assert [m["segments"][0]["content"] for m in chat.restored_messages] == [
        "first",
        "custom prefix",
        "original",
        "original reply",
    ]
    assert chat.actions[-1].get("active_read_only", False) is False

    # Closing a trusted writable position preserves a legitimate model-only
    # change before entering the incompatible display-only branch.
    changed = [*expected, {"role": "user", "content": "local model change"}]
    adapter.turns = changed
    save_calls: list[bool] = []
    controller._save_callbacks.append(lambda values: save_calls.append(True))
    await controller.handle_navigate(2, "next", request_id="foreign-again")
    assert recorder.record.active_leaf == unavailable
    assert recorder.read_only_reason == "model_unavailable"
    assert adapter.turns == changed
    assert save_calls == []
    assert (
        recorder.record.nodes[unavailable].model_dump()["state"]
        == original_outgoing
    )
    saved = store.put_calls[-1][1]
    assert (
        saved.nodes[original].state[TURNS_STATE_KEY]
        == recorder.record.nodes[original].state[TURNS_STATE_KEY]
    )
    assert saved.nodes[unavailable].model_dump()["state"] == original_outgoing
    await controller.handle_navigate(2, "prev", request_id="recover-again")
    assert recorder.record.active_leaf == original
    assert not recorder.read_only
    assert adapter.turns == changed
    assert observations[-1] == ({"tab": "original"}, changed)
    assert save_calls == []


@pytest.mark.anyio
async def test_kvte_notsent_incompatible_detour_can_browse_compatible_checkpoint() -> (
    None
):
    controller, _store = _make_controller()
    record, original, failed = _record_with_browsable_failure()
    record.nodes[original].state[TURNS_STATE_KEY].kind = "unsupported"
    record.set_active_leaf(record.root_id)
    record.open_exchange("compatible", _stored_message("user", "compatible"))
    record.finish_exchange("compatible", "ok", None)
    record.nodes["compatible"].checkpoint = "valid"
    record.nodes["compatible"].state[TURNS_STATE_KEY] = StateEntry(
        kind="turns",
        version=1,
        mode="delta",
        data=cast(JsonValue, _turns("model-only compatible")),
    )
    record.nodes["compatible"].state[VALUES_STATE_KEY] = StateEntry(
        kind="values", version=1, mode="snapshot", data={"tab": "compatible"}
    )
    record.set_active_leaf(failed)
    await replay_exchange_record(controller, record)
    recorder = controller._exchange_recorder
    assert recorder.record is not None
    adapter = cast(_FakeAdapter, controller.adapter)
    sentinel = _turns("poisoned live model")
    adapter.turns = list(sentinel)
    failed_before = recorder.record.nodes[failed].model_dump()
    observations: list[tuple[dict[str, Any], list[dict[str, Any]]]] = []
    controller._restore_callbacks.append(
        lambda values: observations.append((dict(values), list(adapter.turns)))
    )

    await controller.handle_navigate(0, "prev", request_id="unavailable")
    assert recorder.record.active_leaf == original
    assert recorder.read_only_reason == "model_unavailable"
    assert not recorder.continuation_allowed
    assert adapter.turns == sentinel
    assert [
        m["segments"][0]["content"]
        for m in cast(_FakeChat, controller.chat).restored_messages
    ] == ["B"]
    await controller.handle_navigate(0, "next", request_id="failed")
    assert recorder.record.active_leaf == failed
    assert recorder.read_only_reason == "model_unavailable"
    assert not recorder.continuation_allowed
    assert adapter.turns == sentinel

    await controller.handle_navigate(0, "next", request_id="compatible")

    assert recorder.record.active_leaf == "compatible"
    assert adapter.turns == _turns("model-only compatible")
    assert observations[-1] == (
        {"tab": "compatible"},
        _turns("model-only compatible"),
    )
    assert recorder.record.nodes[failed].model_dump() == failed_before
    assert not recorder.read_only
    assert recorder.continuation_allowed


@pytest.mark.anyio
@pytest.mark.parametrize("kind", ["retry", "edit"])
async def test_kvte_notsent_after_unavailable_detour_restores_parent_before_admission(
    request: pytest.FixtureRequest, kind: str
) -> None:
    view = _view(request, InMemoryConversationStore())
    await view.initialize()
    record, original, failed = _record_with_browsable_failure()
    record.nodes[original].state[TURNS_STATE_KEY].kind = "unsupported"
    record.nodes[record.root_id].state[VALUES_STATE_KEY] = StateEntry(
        kind="values", version=1, mode="snapshot", data={"tab": "parent"}
    )
    await view.controller._restore_initial_exchange_record(record)
    recorder = view.controller._exchange_recorder
    assert recorder.record is not None
    live = recorder.record
    sentinel = _turns("poisoned live model")
    view.controller.adapter.set_turns_json(cast(list[TurnDict], sentinel))
    observed: list[tuple[dict[str, Any], list[dict[str, Any]]]] = []
    view.controller._restore_callbacks.append(
        lambda values: observed.append(
            (
                dict(values),
                [
                    dict(turn)
                    for turn in view.controller.adapter.get_turns_json()
                ],
            )
        )
    )
    await view.controller.handle_navigate(0, "prev", request_id="unavailable")
    assert recorder.read_only_reason == "model_unavailable"
    assert not recorder.continuation_allowed
    assert view.controller.adapter.get_turns_json() == sentinel
    await view.controller.handle_navigate(0, "next", request_id="failed")
    assert live.active_leaf == failed
    assert recorder.read_only_reason == "model_unavailable"
    # Advertisement must classify saved parent state, not read or capture
    # the poisoned live client merely to determine whether Retry is possible.
    with patch.object(
        view.controller.adapter,
        "get_turns_json",
        side_effect=AssertionError("metadata captured live turns"),
    ):
        assert view.controller._can_resubmit_active()
        await view.controller.send_history_update()
    update = _history_updates(view.session)[-1]
    assert update["active_read_only_reason"] == "model_unavailable"
    assert update["active_can_resubmit"] is True
    assert not recorder.continuation_allowed
    assert view.controller.adapter.get_turns_json() == sentinel

    if kind == "retry":
        await view.controller.handle_resubmit(0, "retry", request_id="recover")
        expected_text = "B-prime"
    else:
        await view.controller.handle_edit(
            0, "edited replacement", request_id="recover"
        )
        expected_text = "edited replacement"
    assert live.active_leaf not in (failed, original)
    assert observed[-1] == ({"tab": "parent"}, [])
    assert view.controller.adapter.get_turns_json() == []
    assert not recorder.read_only
    assert recorder.continuation_allowed
    with reactive.isolate():
        user = view.chat.user_input()
        assert user is not None and user.text == expected_text
    assert view.chat._transcript.open_exchange_id == live.active_leaf


@pytest.mark.anyio
@pytest.mark.parametrize("parent_issue", ["unavailable_model", "malformed"])
async def test_kvte_notsent_recovery_rejects_unusable_parent_before_staging(
    request: pytest.FixtureRequest, parent_issue: str
) -> None:
    view = _view(request, InMemoryConversationStore())
    await view.initialize()
    record, _original, failed = _record_with_browsable_failure()
    await view.controller._restore_initial_exchange_record(record)
    recorder = view.controller._exchange_recorder
    assert recorder.record is not None
    live = recorder.record
    if parent_issue == "unavailable_model":
        live.nodes[live.root_id].state[TURNS_STATE_KEY].kind = "unsupported"
    else:
        live.nodes[live.root_id].state["unknown:state"] = StateEntry(
            kind="unknown", version=1, mode="snapshot", data={}
        )
    recorder.mark_read_only("model_unavailable")
    before = live.model_dump()
    transcript = view.chat._transcript.read()
    assert not view.controller._can_resubmit_active()
    await view.controller.send_history_update()
    update = _history_updates(view.session)[-1]
    assert not update.get("active_can_resubmit", False)
    assert update["active_read_only_reason"] == "model_unavailable"
    await view.controller._send_exchange_metadata()
    metadata = [
        message["action"]
        for message in view.session.messages
        if message["action"]["type"] == "update_exchange_metadata"
    ][-1]
    assert metadata["data"][0]["retryable"] is False

    with pytest.raises(ValueError, match="[Uu]navailable|[Uu]nsupported"):
        await view.controller.handle_resubmit(0, "retry", request_id="unusable")

    assert live.model_dump() == before
    assert live.active_leaf == failed
    assert view.chat._transcript.read() == transcript
    assert recorder.read_only_reason == "model_unavailable"
    assert not recorder.continuation_allowed
    assert view.provider_inputs == []
    assert view.chat._transcript.open_exchange_id is None
    with reactive.isolate():
        assert view.chat.user_input() is None
        assert view.chat._normal_user_submission() is None


@pytest.mark.anyio
async def test_kvte_model_recovery_never_clears_without_app_restore() -> None:
    controller, _chat, adapter, _store, original, outgoing = (
        _make_v2_navigation_controller()
    )
    recorder = controller._exchange_recorder
    record = recorder.record
    assert record is not None
    recorder.mark_read_only("model_unavailable")
    adapter.turns = _turns("untrusted")
    calls: list[dict[str, Any]] = []

    def fail(values: dict[str, Any]) -> None:
        calls.append(dict(values))
        raise ValueError("app restore failed")

    controller._restore_callbacks.append(fail)
    with pytest.warns(UserWarning, match="on_restore callback failed"):
        await controller.handle_navigate(2, "prev", request_id="app-fails")
    assert calls == [{}]
    assert record.active_leaf == original
    assert recorder.read_only
    assert recorder.read_only_reason == "model_unavailable"
    assert not recorder.continuation_allowed
    assert adapter.turns == [
        {"role": "system", "content": "bootstrap"},
        {"role": "user", "content": "first"},
        {"role": "user", "content": "original"},
    ]
    assert record.nodes[outgoing].state[TURNS_STATE_KEY].data == _turns(
        "replacement"
    )


@pytest.mark.anyio
async def test_kvte_invalid_live_context_stays_displayed_and_blocked() -> None:
    controller, chat, adapter, _store, original, outgoing = (
        _make_v2_navigation_controller()
    )
    recorder = controller._exchange_recorder
    record = recorder.record
    assert record is not None
    recorder.mark_read_only("model_unavailable")
    callbacks: list[dict[str, Any]] = []
    broken = True
    outgoing_state = record.nodes[outgoing].model_dump()["state"]

    def invalid_model(values: dict[str, Any]) -> None:
        callbacks.append(dict(values))
        if broken:
            adapter.turns = [{"role": "user", "content": object()}]

    controller._restore_callbacks.append(invalid_model)
    with pytest.warns(UserWarning, match="model"):
        await controller.handle_navigate(2, "prev", request_id="invalid-live")

    assert callbacks == [{}]
    assert recorder.record is record
    assert record.active_leaf == original
    assert recorder.read_only and not recorder.continuation_allowed
    assert recorder.read_only_reason == "model_unavailable"
    assert [m["segments"][0]["content"] for m in chat.restored_messages] == [
        "first",
        "custom prefix",
        "original",
        "original reply",
    ]

    broken = False
    await controller.handle_navigate(2, "next", request_id="fixed-live-model")
    assert record.active_leaf == outgoing
    assert adapter.turns == [
        {"role": "system", "content": "bootstrap"},
        {"role": "user", "content": "first"},
        {"role": "user", "content": "replacement"},
    ]
    assert callbacks == [{}, {}]
    assert record.nodes[outgoing].model_dump()["state"] == outgoing_state
    assert not recorder.read_only
    assert recorder.continuation_allowed


@pytest.mark.anyio
async def test_kvte_active_stream_blocks_browse_and_retry_recovery(
    request: pytest.FixtureRequest,
) -> None:
    view = _view(request, InMemoryConversationStore())
    await view.initialize()
    record, _original, failed = _record_with_browsable_failure()
    await view.controller._restore_initial_exchange_record(record)
    recorder = view.controller._exchange_recorder
    assert recorder.record is not None
    live = recorder.record
    recorder.mark_read_only("model_unavailable")
    before = live.model_dump()

    with session_context(cast(Any, view.session)), reactive.isolate():
        async with view.chat.message_stream_context() as stream:
            await stream.append("live producer")
            assert not view.controller._can_resubmit_active()
            with pytest.raises(RuntimeError, match="stream is active"):
                await view.controller.handle_navigate(
                    0, "prev", request_id="browse-active"
                )
            with pytest.raises(RuntimeError, match="stream is active"):
                await view.controller.handle_resubmit(
                    0, "retry", request_id="retry-active"
                )
            assert live.model_dump() == before
            assert live.active_leaf == failed
            assert recorder.read_only_reason == "model_unavailable"
            assert not recorder.continuation_allowed
            assert view.chat._transcript.active_stream_id is not None
            assert view.chat.user_input() is None
    assert live.model_dump() == before
    assert recorder.read_only_reason == "model_unavailable"
    assert not recorder.continuation_allowed


@pytest.mark.anyio
@pytest.mark.parametrize("reason", ["interrupted", "model_unavailable"])
async def test_kvte_source_isolation_never_clears_on_compatible_browse(
    reason: ReadOnlyReason,
) -> None:
    controller, _chat, adapter, store, original, _outgoing = (
        _make_v2_navigation_controller()
    )
    recorder = controller._exchange_recorder
    record = recorder.record
    assert record is not None
    recorder.install_restored_record(
        record,
        read_only=True,
        source_isolated=True,
        read_only_reason=reason,
    )
    sentinel = _turns("isolated producer context")
    adapter.turns = list(sentinel)
    writes = len(store.put_calls)
    observed: list[dict[str, Any]] = []
    controller._restore_callbacks.append(
        lambda values: observed.append(dict(values))
    )

    await controller.handle_navigate(2, "prev", request_id="isolated")

    assert record.active_leaf == original
    assert observed == [{}]
    assert adapter.turns == sentinel
    assert recorder.source_isolated and recorder.read_only
    assert recorder.read_only_reason == reason
    assert not recorder.continuation_allowed
    assert len(store.put_calls) == writes


@pytest.mark.anyio
@pytest.mark.parametrize("failure", ["callback", "invalid_model"])
async def test_kvte_failed_parent_recovery_never_admits_input(
    request: pytest.FixtureRequest, failure: str
) -> None:
    view = _view(request, InMemoryConversationStore())
    await view.initialize()
    record, _original, failed = _record_with_browsable_failure()
    await view.controller._restore_initial_exchange_record(record)
    recorder = view.controller._exchange_recorder
    assert recorder.record is not None
    live = recorder.record
    recorder.mark_read_only("model_unavailable")
    assert view.controller._can_resubmit_active()
    observed: list[list[dict[str, Any]]] = []

    def fail(_values: dict[str, Any]) -> None:
        observed.append(
            [dict(turn) for turn in view.controller.adapter.get_turns_json()]
        )
        if failure == "callback":
            raise ValueError("app failed")
        view.controller.adapter.set_turns_json(
            [{"role": "user", "content": cast(Any, object())}]
        )

    view.controller._restore_callbacks.append(fail)
    warning = (
        "on_restore callback failed"
        if failure == "callback"
        else "recorded but not sent"
    )
    with pytest.warns(UserWarning, match=warning):
        await view.controller.handle_resubmit(
            0, "retry", request_id="parent-failure"
        )

    assert observed == [[]]
    assert live.active_leaf not in (None, failed)
    assert (
        live.nodes[live.active_leaf].parent_id == live.nodes[failed].parent_id
    )
    for node_id in (failed, live.active_leaf):
        node = live.nodes[node_id]
        assert node.status == "error" and node.checkpoint == "invalid"
        assert node.not_sent is True
    assert recorder.read_only_reason == "model_unavailable"
    assert not recorder.continuation_allowed
    assert view.chat._transcript.open_exchange_id is None
    with reactive.isolate():
        assert view.chat.user_input() is None
        assert view.chat._normal_user_submission() is None
    assert view.provider_inputs == []


@pytest.mark.anyio
@pytest.mark.parametrize("kind", ["retry", "edit"])
async def test_kvte_model_restriction_does_not_allow_resubmit_of_accepted_error(
    request: pytest.FixtureRequest, kind: str
) -> None:
    view = _view(request, InMemoryConversationStore())
    await view.initialize()
    record, _original, failed = _record_with_browsable_failure()
    record.nodes[failed].not_sent = None
    record.nodes[failed].checkpoint = "valid"
    await view.controller._restore_initial_exchange_record(record)
    recorder = view.controller._exchange_recorder
    assert recorder.record is not None
    live = recorder.record
    recorder.mark_read_only("model_unavailable")
    before = live.model_dump()
    assert not view.controller._can_resubmit_active()

    with pytest.raises(RuntimeError, match="model context is unavailable"):
        if kind == "retry":
            await view.controller.handle_resubmit(
                0, "retry", request_id="blocked"
            )
        else:
            await view.controller.handle_edit(
                0, "blocked edit", request_id="blocked"
            )

    assert live.model_dump() == before
    assert recorder.read_only_reason == "model_unavailable"
    assert not recorder.continuation_allowed
    assert view.chat._transcript.open_exchange_id is None
    with reactive.isolate():
        assert view.chat.user_input() is None
    assert view.provider_inputs == []
