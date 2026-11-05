"""The transition protocol must preserve a draft when resubmission is refused."""

from __future__ import annotations

from typing import Any, Awaitable, Callable, Iterator, cast
from unittest.mock import patch

import pytest
from shiny import reactive
from shiny.module import ResolvedId
from shiny.session import session_context
from shinychat import Chat
from shinychat._history import HistoryInputIds
from shinychat._history_store import ConversationPartition
from shinychat._history_types import CapturedMessage, new_conversation_record_v2
from shinychat.types import HistoryOptions
from test_chat_history import (
    _capture_history_effects,
    _LiveSession,
    _MockClient,
)
from test_history_controller import (
    _make_v2_resubmit_controller,
    _seed_resubmit_transcript,
    _stored_message,
    _wire_resubmit_capture,
)


@pytest.fixture
def transition() -> Iterator[
    tuple[Chat, _LiveSession, dict[str, Callable[[], Awaitable[None]]]]
]:
    session = _LiveSession()
    handlers: dict[str, Callable[[], Awaitable[None]]] = {}
    with (
        patch.object(reactive, "effect", _capture_history_effects(handlers)),
        session_context(cast(Any, session)),
    ):
        chat = Chat(
            "rejection",
            client=cast(Any, _MockClient()),
            history=HistoryOptions(
                store="memory", scope="test", restore_mode="none"
            ),
        )
    controller = chat.history._controller
    assert controller is not None
    controller.partition = ConversationPartition(
        chat_id="rejection", scope="test"
    )
    chat.history._initial_history_initialized = True
    yield chat, session, handlers
    chat.destroy()


def _record(chat: Chat, *, status: str = "ok") -> Any:
    controller = chat.history._controller
    assert controller is not None
    record = new_conversation_record_v2(
        title="test", id="c_test", client_info={}
    )
    record.open_exchange("first", _stored_message("user", "original"))
    record.finish_exchange("first", cast(Any, status), None)
    record.nodes["first"].checkpoint = "valid"
    controller._exchange_recorder.record = record
    return record


async def _invoke(
    transition: tuple[
        Chat, _LiveSession, dict[str, Callable[[], Awaitable[None]]]
    ],
    operation: str,
    payload: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[Any]]:
    chat, session, handlers = transition
    ids = HistoryInputIds.for_chat(ResolvedId("rejection"))
    with session_context(cast(Any, session)):
        cast(Any, session.input[getattr(ids, f"message_{operation}")])._set(
            payload
        )
    with patch("shiny.ui.notification_show") as notification:
        with reactive.isolate():
            await handlers[f"_on_{operation}"]()
    return [m["action"] for m in session.messages], notification.call_args_list


def _payload(kind: str) -> tuple[str, dict[str, Any]]:
    if kind == "edit":
        return "edit", {
            "index": 0,
            "content": "draft",
            "attachments": [],
            "requestId": "req",
        }
    return "resubmit", {"index": 0, "kind": kind, "requestId": "req"}


def _assert_refused(
    actions: list[dict[str, Any]], notifications: list[Any]
) -> None:
    assert [action["type"] for action in actions] == [
        "history_transition_rejected",
        "history_transition_complete",
    ]
    rejected, completed = actions
    assert rejected["requestId"] == completed["requestId"] == "req"
    assert isinstance(rejected["reason"], str) and rejected["reason"]
    assert notifications[0].args[0] == rejected["reason"]
    assert len(notifications) == 1
    assert "history_edit_projection" not in [a["type"] for a in actions]


@pytest.mark.anyio
@pytest.mark.parametrize("kind", ["edit", "retry", "regenerate"])
async def test_invalid_parent_rejects_before_projection(
    transition: Any, kind: str
) -> None:
    chat = transition[0]
    record = _record(chat, status="cancelled" if kind == "retry" else "ok")
    record.nodes[record.root_id].checkpoint = "invalid"
    before = record.model_dump()
    operation, payload = _payload(kind)
    actions, notifications = await _invoke(transition, operation, payload)
    _assert_refused(actions, notifications)
    assert record.model_dump() == before
    assert "state" in actions[0]["reason"].lower()


@pytest.mark.anyio
@pytest.mark.parametrize("kind", ["edit", "retry", "regenerate"])
@pytest.mark.parametrize(
    "case", ["gate", "partition", "missing", "index", "read_only"]
)
async def test_refusals_preserve_the_draft(
    transition: Any, kind: str, case: str
) -> None:
    chat = transition[0]
    controller = chat.history._controller
    assert controller is not None
    record = _record(chat, status="cancelled" if kind == "retry" else "ok")
    operation, payload = _payload(kind)
    if case == "gate":
        chat.history._initial_history_initialized = False
    elif case == "partition":
        controller.partition = None
    elif case == "missing":
        controller._exchange_recorder.record = None
    elif case == "index":
        payload["index"] = 9
    else:
        controller._exchange_recorder.mark_read_only("interrupted")
    before = record.model_dump()
    actions, notifications = await _invoke(transition, operation, payload)
    _assert_refused(actions, notifications)
    assert record.model_dump() == before


@pytest.mark.anyio
@pytest.mark.parametrize("error_type", [ValueError, RuntimeError])
@pytest.mark.parametrize("kind", ["edit", "retry", "regenerate"])
async def test_unexpected_failure_uses_generic_toast_not_exception_text(
    transition: Any,
    kind: str,
    error_type: type[Exception],
) -> None:
    chat = transition[0]
    controller = chat.history._controller
    assert controller is not None
    _record(chat, status="cancelled" if kind == "retry" else "ok")
    operation, payload = _payload(kind)
    with patch.object(
        controller, "resubmit", side_effect=error_type("private error detail")
    ):
        with pytest.warns(UserWarning, match="private error detail"):
            actions, notifications = await _invoke(
                transition, operation, payload
            )
    assert [a["type"] for a in actions] == ["history_transition_complete"]
    assert "private error detail" not in str(notifications)
    assert len(notifications) == 1


@pytest.mark.anyio
@pytest.mark.parametrize("kind", ["unknown", "regenerate", "retry"])
async def test_invalid_resubmit_kind_or_status_is_refused(
    transition: Any, kind: str
) -> None:
    _record(transition[0], status="cancelled" if kind == "regenerate" else "ok")
    operation, payload = _payload(kind)
    actions, notifications = await _invoke(transition, operation, payload)
    _assert_refused(actions, notifications)


async def _seed_branch(transition: Any, *, kind: str) -> Any:
    chat = transition[0]
    controller = chat.history._controller
    assert controller is not None
    source, _, _, _, first, target = _make_v2_resubmit_controller()
    record = source._exchange_recorder.record
    assert record is not None
    for node_id, content in [(first, "reply one"), (target, "reply two")]:
        record.append_message(
            node_id,
            CapturedMessage.from_stored_message(
                _stored_message("assistant", content), icon=None
            ),
        )
    record.nodes[first].checkpoint = "valid"
    record.nodes[target].checkpoint = "valid"
    record.nodes[target].status = "cancelled" if kind == "retry" else "ok"
    controller._exchange_recorder.record = record
    controller._active_id.set(record.id)
    controller.adapter.set_turns_json(
        [
            {"role": "system", "content": "bootstrap"},
            {"role": "user", "content": "first"},
            {"role": "user", "content": "second"},
        ]
    )
    chat._transcript.set_capture_callbacks(
        on_accepted_input=None,
        on_message_committed=None,
        on_stream_started=None,
        on_stream_updated=None,
        on_stream_finished=None,
    )
    await _seed_resubmit_transcript(chat, first, target)
    _wire_resubmit_capture(controller, chat)
    return record


@pytest.mark.anyio
@pytest.mark.parametrize("kind", ["edit", "retry", "regenerate"])
@pytest.mark.parametrize("fail_after_projection", [False, True])
async def test_staged_projection_is_never_rejected(
    transition: Any, kind: str, fail_after_projection: bool
) -> None:
    chat = transition[0]
    controller = chat.history._controller
    assert controller is not None
    record = await _seed_branch(transition, kind=kind)
    old_leaf = record.active_leaf
    operation, payload = _payload(kind)
    payload["index"] = 2
    if fail_after_projection:

        def fail(_values: dict[str, Any]) -> None:
            raise RuntimeError("private restore detail")

        controller._restore_callbacks.append(fail)
        with pytest.warns(UserWarning, match="private restore detail"):
            actions, notifications = await _invoke(
                transition, operation, payload
            )
    else:
        actions, notifications = await _invoke(transition, operation, payload)
    types = [action["type"] for action in actions]
    assert types.count("history_edit_projection") == 1, actions
    assert "history_transition_rejected" not in types
    assert types[-1] == "history_transition_complete"
    assert actions[-1]["requestId"] == "req"
    assert record.active_leaf != old_leaf
    projection = next(
        a for a in actions if a["type"] == "history_edit_projection"
    )
    assert projection["requestId"] == "req"
    assert projection["exchange_id"] == record.active_leaf
    staged = record.nodes[record.active_leaf]
    if fail_after_projection:
        assert staged.not_sent is True
        assert "private restore detail" not in str(notifications)
    else:
        assert staged.not_sent is not True
        with reactive.isolate():
            assert chat.user_input() is not None


@pytest.mark.anyio
@pytest.mark.parametrize("operation", ["edit", "resubmit"])
@pytest.mark.parametrize("bad_index", [None, "0", True, -1])
async def test_invalid_index_refuses_without_mutation(
    transition: Any, operation: str, bad_index: Any
) -> None:
    record = _record(transition[0])
    before = record.model_dump()
    _, payload = _payload("edit" if operation == "edit" else "regenerate")
    payload["index"] = bad_index
    actions, notifications = await _invoke(transition, operation, payload)
    _assert_refused(actions, notifications)
    assert record.model_dump() == before


@pytest.mark.anyio
async def test_rejection_delivery_failure_still_completes(
    transition: Any,
) -> None:
    chat = transition[0]
    record = _record(chat)
    record.nodes[record.root_id].checkpoint = "invalid"
    original = chat._send_action

    async def send(action: Any) -> None:
        if action["type"] == "history_transition_rejected":
            raise RuntimeError("delivery failed")
        await original(action)

    chat._send_action = send  # type: ignore[method-assign]
    operation, payload = _payload("edit")
    actions, notifications = await _invoke(transition, operation, payload)
    assert actions == [
        {"type": "history_transition_complete", "requestId": "req"}
    ]
    assert len(notifications) == 1


@pytest.mark.parametrize("case", ["unknown", "root", "off_path"])
def test_direct_invalid_target_refusal_does_not_expose_record_identifiers(
    transition: Any, case: str
) -> None:
    chat = transition[0]
    controller = chat.history._controller
    assert controller is not None
    record = _record(chat)
    if case == "unknown":
        target = "private-exchange-id"
    elif case == "root":
        target = record.root_id
    else:
        target = "first"
        record.open_exchange(
            "selected",
            _stored_message("user", "branch"),
            parent_id=record.root_id,
        )
    before = record.model_dump()
    from shinychat._history_controller import _ResubmitRejected

    with pytest.raises(_ResubmitRejected) as rejected:
        controller._validate_resubmit_target(record, target, "edit")
    assert "private-exchange-id" not in rejected.value.reason
    assert record.model_dump() == before


@pytest.mark.anyio
@pytest.mark.parametrize("kind", ["edit", "retry", "regenerate"])
async def test_failure_after_commit_keeps_projection_and_generic_notification(
    transition: Any, kind: str
) -> None:
    chat = transition[0]
    record = await _seed_branch(transition, kind=kind)
    original = chat._record_accepted_user_input_with_capture

    async def fail_after_commit(*args: Any, **kwargs: Any) -> None:
        await original(*args, **kwargs)
        raise RuntimeError("private post-commit detail")

    chat._record_accepted_user_input_with_capture = fail_after_commit  # type: ignore[method-assign]
    operation, payload = _payload(kind)
    payload["index"] = 2
    with pytest.warns(UserWarning, match="private post-commit detail"):
        actions, notifications = await _invoke(transition, operation, payload)
    types = [a["type"] for a in actions]
    assert types.count("history_edit_projection") == 1
    assert "history_transition_rejected" not in types
    assert actions[-1] == {
        "type": "history_transition_complete",
        "requestId": "req",
    }
    assert record.nodes[record.active_leaf].not_sent is not True
    assert len(notifications) == 1
    assert "private post-commit detail" not in str(notifications)


@pytest.mark.anyio
@pytest.mark.parametrize("kind", ["edit", "retry", "regenerate"])
@pytest.mark.parametrize("error_type", [ValueError, RuntimeError])
async def test_preflight_exception_is_not_misclassified_as_safe_refusal(
    transition: Any, kind: str, error_type: type[Exception]
) -> None:
    record = _record(
        transition[0], status="cancelled" if kind == "retry" else "ok"
    )
    record.nodes[record.root_id].checkpoint = "valid"
    before = record.model_dump()
    operation, payload = _payload(kind)
    with patch(
        "shinychat._history_plan.validate_active_path_state",
        side_effect=error_type("private preflight detail"),
    ):
        with pytest.warns(UserWarning, match="private preflight detail"):
            actions, notifications = await _invoke(
                transition, operation, payload
            )
    assert actions == [
        {"type": "history_transition_complete", "requestId": "req"}
    ]
    assert len(notifications) == 1
    assert "private preflight detail" not in str(notifications)
    assert record.model_dump() == before
