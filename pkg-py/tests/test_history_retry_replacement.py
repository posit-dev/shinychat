"""Retry and Edit of a failed attempt open a new sibling."""

import asyncio
from pathlib import Path
from typing import Any

import pytest
from shinychat._history_store import (
    ConversationStore,
    FileConversationStore,
    InMemoryConversationStore,
)
from shinychat._history_types import (
    VALUES_STATE_KEY,
    node_is_terminal_incomplete,
)
from test_history_node_first_review import _producer, _record, _stored


@pytest.fixture(params=["file", "memory"])
def retry_store(
    request: pytest.FixtureRequest, tmp_path: Path
) -> ConversationStore:
    if request.param == "file":
        return FileConversationStore(tmp_path)
    return InMemoryConversationStore()


@pytest.mark.anyio
@pytest.mark.parametrize("kind", ["edit", "not_sent_retry", "provider_retry"])
async def test_edit_and_retry_create_siblings(
    request: pytest.FixtureRequest, retry_store: ConversationStore, kind: str
) -> None:
    record = _record(failed_parent="original")
    if kind == "provider_retry":
        record.nodes["failed"].not_sent = None
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
        assert original_after.pop("state").get(VALUES_STATE_KEY) == before.pop(
            "state"
        ).get(VALUES_STATE_KEY)
    assert original_after == before
    assert live.nodes["original"].children == [*children, new_id]
    assert live.nodes[new_id].parent_id == "original"


@pytest.mark.anyio
@pytest.mark.parametrize("failure", ["edit_cancel", "retry_fatal"])
async def test_fatal_resubmit_failures_keep_interrupted_reading(
    request: pytest.FixtureRequest, retry_store: ConversationStore, failure: str
) -> None:
    view = await _producer(
        request,
        retry_store,
        _record(failed_parent="original"),
    )
    blocked = asyncio.Event()
    never = asyncio.Event()

    async def fail_rewind(_context: Any) -> None:
        blocked.set()
        if failure == "retry_fatal":
            raise SystemExit("fatal preparation")
        await never.wait()

    view.controller._exchange_recorder._register_rewind_hook(
        "test:fail", fail_rewind
    )
    if failure == "edit_cancel":
        task = asyncio.create_task(
            view.controller.handle_edit(2, "new edit", request_id="edit")
        )
        await asyncio.wait_for(blocked.wait(), timeout=5)
        task.cancel("edit cancellation")
        with pytest.raises(asyncio.CancelledError, match="edit cancellation"):
            await task
    else:
        with pytest.raises(SystemExit, match="fatal preparation"):
            await view.controller.handle_resubmit(
                2, "retry", request_id="fatal"
            )
    stored = await _stored(retry_store)
    assert stored.active_leaf is not None
    assert stored.nodes[stored.active_leaf].status == "pending"
    assert stored.nodes[stored.active_leaf].not_sent is None
    assert view.controller._unresolved_record(stored)
    assert node_is_terminal_incomplete(stored.nodes["failed"])
    assert view.controller._exchange_recorder.record is None
    assert view.provider_inputs == []
