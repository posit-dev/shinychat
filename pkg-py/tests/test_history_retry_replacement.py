"""Not-sent Retry replaces one bookmarked logical version."""

import asyncio
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, cast
from unittest.mock import AsyncMock, patch

import pytest
from shiny import reactive
from shiny.session import session_context
from shinychat._attachments import Attachment
from shinychat._chat_transcript import StagedInputAdmission, TranscriptEntry
from shinychat._history_plan import materialize_restore_turns
from shinychat._history_store import (
    ConversationStore,
    FileConversationStore,
    InMemoryConversationStore,
)
from shinychat._history_types import (
    HISTORY_ERROR_NOT_SENT,
    TURNS_STATE_KEY,
    VALUES_STATE_KEY,
    CapturedMessage,
    ExchangeNode,
    StateEntry,
    node_is_terminal_incomplete,
)
from test_history_controller import _sent, _stored_message
from test_history_node_first_review import (
    _contents,
    _producer,
    _record,
    _stored,
    _view,
)


@pytest.fixture(params=["file", "memory"])
def retry_store(
    request: pytest.FixtureRequest, tmp_path: Path
) -> ConversationStore:
    if request.param == "file":
        return FileConversationStore(tmp_path)
    return InMemoryConversationStore()


@pytest.mark.anyio
async def test_retry_reuses_bookmarked_leaf_through_failures_and_success(
    request: pytest.FixtureRequest, retry_store: ConversationStore
) -> None:
    record = _record(availability="complete", failed_parent="original")
    failed = record.nodes["failed"]
    assert failed.input is not None
    attachment = Attachment.from_data(b"hello", "text/plain", name="notes.txt")
    failed.input.attachments = [attachment]
    failed.state[TURNS_STATE_KEY] = StateEntry(
        kind="turns",
        version=1,
        mode="snapshot",
        data=[{"role": "user", "content": "stale"}],
    )
    record.nodes["failed"] = ExchangeNode.model_validate(
        {
            **failed.model_dump(),
            "future_node_field": {"value": 7},
            "future_null": None,
        }
    )
    record.set_active_leaf("original")
    record.open_exchange("other-child", _stored_message("user", "other child"))
    record.finish_exchange("other-child", "ok", None)
    record.nodes["other-child"].checkpoint = "valid"
    record.set_active_leaf("failed")
    original_children = list(record.nodes["original"].children)
    original_sequence = record.next_node_seq
    created_at = record.nodes["failed"].created_at
    original_other = record.nodes["other-child"].model_dump()
    producer = await _producer(request, retry_store, record)
    pointer = await producer.stamp()
    assert pointer == {"conversation_id": "c_review", "node_id": "failed"}

    for attempt in (1, 2):

        def restore(_values: dict[str, Any]) -> None:
            raise RuntimeError("restore still broken")

        producer.chat.history.on_restore(restore)
        producer.chat.history.on_save(
            lambda values: values.update({"attempt": attempt})
        )
        live = producer.controller._exchange_recorder.record
        assert live is not None
        live.updated_at = datetime(2000, 1, 1, tzinfo=timezone.utc)
        staged: list[tuple[datetime, dict[str, Any]]] = []
        send_action = producer.chat._send_action

        async def inspect_projection(
            action: Any, *args: Any, **kwargs: Any
        ) -> None:
            if action["type"] == "history_edit_projection":
                current = producer.controller._exchange_recorder.record
                assert current is not None
                staged.append(
                    (current.updated_at, current.nodes["failed"].model_dump())
                )
            await send_action(action, *args, **kwargs)

        producer.chat._send_action = inspect_projection  # type: ignore[method-assign]
        with pytest.warns(UserWarning, match="on_restore callback failed"):
            await producer.controller.handle_resubmit(
                2, "retry", request_id=f"fail-{attempt}"
            )
        live = producer.controller._exchange_recorder.record
        assert live is not None
        assert live.active_leaf == "failed"
        assert len(staged) == 1
        staged_at, staged_node = staged[0]
        assert staged_at > datetime(2000, 1, 1, tzinfo=timezone.utc)
        assert staged_node["status"] == "pending"
        assert staged_node["checkpoint"] == "candidate"
        assert staged_node["error"] is None
        assert staged_node["not_sent"] is None
        assert staged_node["app_values"] is None
        assert staged_node["state"] == {}
        node = live.nodes["failed"]
        assert node_is_terminal_incomplete(node)
        assert node.state[VALUES_STATE_KEY].data == {"attempt": attempt}
        assert TURNS_STATE_KEY not in node.state
        assert node.created_at == created_at
        assert node.model_extra == {
            "future_node_field": {"value": 7},
            "future_null": None,
        }
        assert node.input is not None and node.input.attachments == [attachment]
        assert live.nodes["original"].children == original_children
        assert live.nodes["original"].selected_child == "failed"
        assert live.nodes["other-child"].model_dump() == original_other
        assert live.next_node_seq == original_sequence
        with reactive.isolate():
            assert producer.chat.user_input() is None
        stored = await _stored(retry_store)
        assert stored.active_leaf == "failed"
        assert stored.nodes["failed"].state[VALUES_STATE_KEY].data == {
            "attempt": attempt
        }
        producer = _view(request, retry_store, pointer=pointer)
        await producer.initialize()
        assert producer.controller._exchange_recorder.record is not None
        assert (
            producer.controller._exchange_recorder.record.active_leaf
            == "failed"
        )
        assert _contents(producer.chat) == [
            "original",
            "original reply",
            "replacement",
        ]

    producer.chat.history.on_save(lambda values: values.update({"attempt": 3}))
    capabilities: list[StagedInputAdmission] = []
    admit = producer.chat._record_accepted_user_input_with_capture

    async def capture_admission(*args: Any, **kwargs: Any) -> None:
        capabilities.append(kwargs["staged_admission"])
        await admit(*args, **kwargs)

    with patch.object(
        producer.chat,
        "_record_accepted_user_input_with_capture",
        capture_admission,
    ):
        await producer.controller.handle_resubmit(
            2, "retry", request_id="success"
        )
    live = producer.controller._exchange_recorder.record
    assert live is not None and live.active_leaf == "failed"
    node = live.nodes["failed"]
    assert node.status == "pending" and node.checkpoint == "candidate"
    assert (
        node.not_sent is None and node.app_values is None and node.error is None
    )
    assert node.state[VALUES_STATE_KEY].data == {"attempt": 3}
    assert node.created_at == created_at
    assert node.model_extra == {
        "future_node_field": {"value": 7},
        "future_null": None,
    }
    assert node.input is not None and node.input.attachments == [attachment]
    assert live.nodes["original"].children == original_children
    assert live.next_node_seq == original_sequence
    with reactive.isolate():
        accepted = producer.chat.user_input()
        assert accepted is not None and accepted.text == "replacement"
    assert len(capabilities) == 1
    assert capabilities[0].committed
    with pytest.raises(RuntimeError, match="already admitted"):
        await producer.chat._transcript.record_staged_input_and_notify(
            capabilities[0], node.input
        )
    with pytest.raises(RuntimeError, match="already admitted"):
        await producer.chat._transcript.record_staged_input_and_notify(
            StagedInputAdmission("failed"), node.input
        )
    with pytest.raises(RuntimeError, match="owned history transaction"):
        await producer.chat._record_accepted_user_input_with_capture(
            node.input,
            staged_admission=StagedInputAdmission("failed"),
            transaction=object(),
        )

    parent_turns = producer.controller.adapter.get_turns_json()
    producer.controller.adapter.set_turns_json(
        [
            *parent_turns,
            {"role": "user", "content": "replacement"},
            {"role": "assistant", "content": "reply"},
        ]
    )
    await producer.chat._transcript.start_stream(
        stream_id="reply",
        entry=TranscriptEntry(message=_stored_message("assistant", "reply")),
        owner_task=None,
        exchange_id="failed",
        send=_sent,
    )
    await producer.chat._transcript.end_stream(
        stream_id="reply", status=None, error=None, send=_sent
    )
    await producer.controller.on_response()
    stored = await _stored(retry_store)
    assert stored.active_leaf == "failed"
    assert stored.nodes["failed"].status == "ok"
    assert stored.nodes["failed"].not_sent is None
    reloaded = _view(request, retry_store, pointer=pointer)
    await reloaded.initialize()
    assert reloaded.controller._exchange_recorder.record is not None
    assert reloaded.controller._exchange_recorder.record.active_leaf == "failed"
    assert _contents(reloaded.chat) == [
        "original",
        "original reply",
        "replacement",
        "reply",
    ]
    assert reloaded.controller.adapter.get_turns_json() == [
        *parent_turns,
        {"role": "user", "content": "replacement"},
        {"role": "assistant", "content": "reply"},
    ]


@pytest.mark.anyio
@pytest.mark.parametrize(
    "unsafe",
    [
        "child",
        "content",
        "orphan",
        "dangling_selection",
        "parent_link",
        "parent_selection",
    ],
)
async def test_retry_does_not_replace_unsafe_failed_node(
    request: pytest.FixtureRequest, retry_store: ConversationStore, unsafe: str
) -> None:
    record = _record(availability="complete", failed_parent="original")
    if unsafe in ("child", "orphan"):
        record.open_exchange(
            "descendant", _stored_message("user", "keep child")
        )
        record.finish_exchange("descendant", "ok", None)
        record.nodes["descendant"].checkpoint = "valid"
        record.set_active_leaf("failed")
        if unsafe == "orphan":
            # A broken child list must not hide a node's parent pointer.
            record.nodes["failed"].children.clear()
    elif unsafe == "content":
        record.nodes["failed"].messages.append(
            CapturedMessage.from_stored_message(
                _stored_message("assistant", "keep content"), icon=None
            )
        )
    elif unsafe == "dangling_selection":
        record.nodes["failed"].selected_child = "missing"
    elif unsafe == "parent_link":
        record.nodes["original"].children.remove("failed")
    else:
        record.nodes["original"].selected_child = None
    before = record.nodes["failed"].model_dump()
    view = await _producer(request, retry_store, record)
    await view.controller.handle_resubmit(2, "retry", request_id="unsafe")
    live = view.controller._exchange_recorder.record
    assert live is not None
    assert live.active_leaf != "failed"
    assert live.nodes["failed"].model_dump() == before
    if unsafe in ("child", "orphan"):
        assert live.nodes["descendant"].parent_id == "failed"


@pytest.mark.anyio
@pytest.mark.parametrize("kind", ["edit", "provider_retry"])
async def test_edit_and_accepted_failure_retry_still_create_siblings(
    request: pytest.FixtureRequest, retry_store: ConversationStore, kind: str
) -> None:
    record = _record(availability="complete", failed_parent="original")
    if kind == "provider_retry":
        record.nodes["failed"].not_sent = None
        record.nodes["failed"].app_values = None
        record.nodes["failed"].checkpoint = "valid"
    before = record.nodes["failed"].model_dump()
    children = list(record.nodes["original"].children)
    view = await _producer(request, retry_store, record)
    if kind == "edit":
        await view.controller.handle_edit(2, "new edit", request_id="edit")
    else:
        await view.controller.handle_resubmit(2, "retry", request_id="retry")

    live = view.controller._exchange_recorder.record
    assert live is not None and live.active_leaf is not None
    new_id = live.active_leaf
    assert new_id != "failed"
    original_after = live.nodes["failed"].model_dump()
    if kind == "provider_retry":
        # The ordinary close-capture can add recorded model context.
        assert (
            original_after.pop("state")[VALUES_STATE_KEY]
            == before.pop("state")[VALUES_STATE_KEY]
        )
    assert original_after == before
    assert live.nodes["original"].children == [*children, new_id]
    assert live.nodes[new_id].parent_id == "original"


@pytest.mark.anyio
async def test_reused_retry_two_failed_writes_keeps_terminal_live_and_old_disk(
    request: pytest.FixtureRequest, retry_store: ConversationStore
) -> None:
    record = _record(availability="complete", failed_parent="original")
    view = await _producer(request, retry_store, record)
    saved_before = (await _stored(retry_store)).model_dump()

    # Both the pending stage write and the subsequent failed-outcome write
    # fail; the old durable record must not claim the new attempt was saved.
    with (
        patch.object(
            retry_store, "put", side_effect=OSError("disk full")
        ) as put,
        patch.object(
            view.controller, "_notify_edit_not_saved", new_callable=AsyncMock
        ) as notify,
    ):
        with pytest.warns(UserWarning, match="recorded but not sent"):
            with pytest.warns(UserWarning, match="could not save"):
                await view.controller.handle_resubmit(
                    2, "retry", request_id="both-puts-fail"
                )
    assert put.await_count == 2
    notify.assert_awaited_once()
    live = view.controller._exchange_recorder.record
    assert live is not None and live.active_leaf == "failed"
    node = live.nodes["failed"]
    assert node.status == "error" and node.checkpoint == "invalid"
    assert node.not_sent is True and node.app_values == "complete"
    assert (
        node.error is not None and node.error.message == HISTORY_ERROR_NOT_SENT
    )
    assert view.controller._exchange_recorder._staged_input is None
    assert view.chat._transcript.open_exchange_id is None
    with reactive.isolate():
        assert view.chat.user_input() is None
        assert view.chat._normal_user_submission() is None
    assert _contents(view.chat) == ["original", "original reply", "replacement"]
    assert (await _stored(retry_store)).model_dump() == saved_before


@pytest.mark.anyio
@pytest.mark.parametrize("failure", ["persistence", "publication"])
async def test_reused_retry_post_commit_failure_never_relabels_not_sent(
    request: pytest.FixtureRequest,
    retry_store: ConversationStore,
    failure: str,
) -> None:
    record = _record(availability="complete", failed_parent="original")
    view = await _producer(request, retry_store, record)
    original_put = retry_store.put

    async def fail_post_commit(*args: Any, **kwargs: Any) -> None:
        if view.chat._transcript.open_exchange_id == "failed":
            raise OSError("injected after commit")
        await original_put(*args, **kwargs)

    if failure == "persistence":
        fault = patch.object(retry_store, "put", side_effect=fail_post_commit)
    else:
        fault = patch.object(
            view.chat,
            "_publish_accepted_user_input",
            side_effect=OSError("injected after commit"),
        )
    with fault, pytest.raises(OSError, match="injected after commit"):
        await view.controller.handle_resubmit(
            2, "retry", request_id="commit-fault"
        )

    live = view.controller._exchange_recorder.record
    assert live is not None and live.active_leaf == "failed"
    node = live.nodes["failed"]
    assert node.status == "pending" and node.checkpoint == "candidate"
    assert (
        node.not_sent is None and node.app_values is None and node.error is None
    )
    assert not node_is_terminal_incomplete(node)
    assert view.chat._transcript.open_exchange_id == "failed"
    assert _contents(view.chat) == ["original", "original reply", "replacement"]
    stored = await _stored(retry_store)
    assert stored.nodes["failed"].status == "pending"
    assert stored.nodes["failed"].not_sent is None
    assert stored.nodes["failed"].error is None


@pytest.mark.anyio
async def test_reused_retry_stream_delivery_failure_is_accepted_error_then_branches(
    request: pytest.FixtureRequest, retry_store: ConversationStore
) -> None:
    record = _record(availability="complete", failed_parent="original")
    view = await _producer(request, retry_store, record)
    await view.controller.handle_resubmit(2, "retry", request_id="reuse")
    recorder = view.controller._exchange_recorder
    live = recorder.record
    assert live is not None and live.active_leaf == "failed"
    accepted = live.nodes["failed"]
    assert accepted.status == "pending" and accepted.not_sent is None
    with reactive.isolate():
        submitted = view.chat.user_input()
        assert submitted is not None and submitted.text == "replacement"
    assert view.chat._transcript.open_exchange_id == "failed"

    transport_actions: list[dict[str, Any]] = []
    reported_errors: list[BaseException] = []
    error_reported = asyncio.Event()
    send = view.session.send_custom_message
    parent_turns = view.controller.adapter.get_turns_json()
    provider_steps: list[str] = []

    async def transport(kind: str, message: object) -> None:
        envelope = cast(dict[str, Any], message)
        action = cast(dict[str, Any], envelope["action"])
        transport_actions.append(dict(action))
        if action.get("type") == "chunk" and action.get("content") == "lost":
            raise OSError("injected stream transport failure")
        await send(kind, message)

    async def report(error: BaseException) -> None:
        reported_errors.append(error)
        error_reported.set()

    async def provider() -> AsyncIterator[str]:
        provider_steps.append("started")
        view.controller.adapter.set_turns_json(
            [
                *parent_turns,
                {"role": "user", "content": "replacement"},
                {"role": "assistant", "content": "provider model context"},
            ]
        )
        yield "kept"
        provider_steps.append("second chunk")
        yield "lost"

    view.chat.on_error = "unhandled"
    with (
        patch.object(
            view.session, "send_custom_message", side_effect=transport
        ),
        patch.object(view.session, "_unhandled_error", side_effect=report),
        session_context(cast(Any, view.session)),
        reactive.isolate(),
    ):
        task = await view.chat.append_message_stream(provider())
        worker = task._task
        assert worker is not None
        with pytest.warns(
            RuntimeWarning,
            match="Error in Effect: injected stream transport failure",
        ):
            with pytest.raises(
                OSError, match="injected stream transport failure"
            ):
                await asyncio.wait_for(worker, timeout=2)
            await asyncio.wait_for(error_reported.wait(), timeout=2)
            # Drain any completion work still running after error reporting.
            completions = tuple(task._done_tasks)
            if completions:
                await asyncio.wait_for(asyncio.gather(*completions), timeout=2)

    assert provider_steps == ["started", "second chunk"]
    actions = [
        (a.get("type"), a.get("content"))
        for a in transport_actions
        if a.get("type") in ("chunk_start", "chunk", "chunk_end")
    ]
    assert actions == [
        ("chunk_start", None),
        ("chunk", "kept"),
        ("chunk", "lost"),
        ("chunk_end", None),
    ]
    delivered = [m["action"] for m in view.session.messages]
    assert any(
        a.get("type") == "chunk" and a.get("content") == "kept"
        for a in delivered
    )
    assert not any(
        a.get("type") == "chunk" and a.get("content") == "lost"
        for a in delivered
    )
    assert len(reported_errors) == 1
    assert isinstance(reported_errors[0], OSError)
    assert str(reported_errors[0]) == "injected stream transport failure"
    node = live.nodes["failed"]
    assert node.status == "error"
    assert (
        node.error is not None and node.error.message != HISTORY_ERROR_NOT_SENT
    )
    assert node.not_sent is None and node.app_values is None
    assert not node_is_terminal_incomplete(node)
    assert node.is_checkpoint
    assert [m.as_stored_message().content for m in node.messages] == ["kept"]
    stored = await _stored(retry_store)
    stored_node = stored.nodes["failed"]
    assert stored_node.status == "error"
    assert (
        stored_node.error is not None
        and stored_node.error.message != HISTORY_ERROR_NOT_SENT
    )
    assert stored_node.not_sent is None and stored_node.app_values is None
    assert "not_sent" not in stored_node.model_dump(exclude_none=True)
    assert "app_values" not in stored_node.model_dump(exclude_none=True)

    # This is now an accepted/provider-failed version, so its Retry branches.
    original = node.model_dump()
    context, unavailable = materialize_restore_turns(
        recorder._turns_path_context(live, "failed"),
        adapter=view.controller.adapter,
    )
    assert unavailable is None
    assert context == [
        *parent_turns,
        {"role": "user", "content": "replacement"},
        {"role": "assistant", "content": "provider model context"},
    ]
    children = list(live.nodes["original"].children)
    await view.controller.handle_resubmit(
        2, "retry", request_id="provider-retry"
    )
    new_id = live.active_leaf
    assert new_id is not None and new_id != "failed"
    assert live.nodes["original"].children == [*children, new_id]
    assert live.nodes[new_id].parent_id == "original"
    original_after = live.nodes["failed"].model_dump()
    # Ordinary outgoing model-only capture may update the saved state.
    original.pop("state")
    original_after.pop("state")
    assert original_after == original
    restored_context, unavailable = materialize_restore_turns(
        recorder._turns_path_context(live, "failed"),
        adapter=view.controller.adapter,
    )
    assert unavailable is None and restored_context == context
    assert live.nodes["failed"].not_sent is None
    assert live.nodes["failed"].status == "error"
    new_input = live.nodes[new_id].input
    assert new_input is not None
    assert new_input.content == "replacement"
