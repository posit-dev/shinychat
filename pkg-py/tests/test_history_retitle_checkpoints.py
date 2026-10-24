"""Delayed automatic titles must not create a new application-state boundary."""

import asyncio
from typing import Any

import pytest
from shinychat._history_types import (
    TURNS_STATE_KEY,
    VALUES_STATE_KEY,
    StateEntry,
)
from test_history_checkpoint_models import _complete_append
from test_history_controller import (
    _make_controller,
    _stored_message,
    _v2_transcript,
    part,
)
from test_history_stream_persistence import _Backend, _saved
from test_history_stream_persistence import backend as _backend_fixture

backend = _backend_fixture


@pytest.mark.anyio
@pytest.mark.parametrize("position", ["leaf", "root", "user_rename"])
async def test_delayed_title_preserves_settled_checkpoints(
    backend: _Backend,
    position: str,
) -> None:
    live = {"value": "settled"}
    app_calls: list[str] = []
    hook_calls: list[str] = []

    def save(values: dict[str, Any]) -> None:
        app_calls.append(live["value"])
        values.update(live)

    controller, _ = _make_controller(store=backend.store, save_callbacks=[save])
    recorder = controller._exchange_recorder

    def capture(context: Any) -> StateEntry:
        hook_calls.append(context.reason)
        return StateEntry(
            kind="test", version=1, mode="snapshot", data=dict(live)
        )

    recorder._register_capture_hook("test:app", capture)
    entered = asyncio.Event()
    title_result: asyncio.Future[str] = (
        asyncio.get_running_loop().create_future()
    )

    async def title(turns: list[dict[str, Any]]) -> str:
        assert turns == [
            {"role": "user", "content": "one"},
            {"role": "assistant", "content": "answer one"},
            {"role": "user", "content": "two"},
            {"role": "assistant", "content": "answer two"},
        ]
        entered.set()
        return await title_result

    controller.title_fn = title
    controller.title_enabled = True
    controller.adapter.set_turns_json([])
    transcript = _v2_transcript(controller)
    sdk: list[Any] = []
    exchange_ids: list[str] = []
    for text in ("one", "two"):
        exchange_id = await transcript.record_accepted_input_and_notify(
            _stored_message("user", text)
        )
        exchange_ids.append(exchange_id)
        sdk.extend(
            [
                {"role": "user", "content": text},
                {"role": "assistant", "content": "answer " + text},
            ]
        )
        controller.adapter.set_turns_json(list(sdk))
        await _complete_append(
            controller, transcript, exchange_id, "answer " + text
        )
        await controller.on_response()

    task = controller._title_task
    assert task is not None
    try:
        await asyncio.wait_for(entered.wait(), timeout=5)
        assert not task.done()
        record = recorder.record
        assert record is not None
        for index, exchange_id in enumerate(exchange_ids, start=1):
            assert record.nodes[exchange_id].checkpoint == "valid"
            assert (
                record.nodes[exchange_id].state[TURNS_STATE_KEY].data
                == sdk[: 2 * index]
            )
        assert record.nodes[record.root_id].state[VALUES_STATE_KEY].data == {
            "value": "settled"
        }
        # Equal APP frames inherit the valid root. A late root capture would
        # change it and pin these children to protect their former values.
        assert all(
            VALUES_STATE_KEY not in record.nodes[key].state
            for key in exchange_ids
        )
        if position == "root":
            async with recorder.lock:
                await recorder.persist_active_leaf_locked(
                    record, record.root_id
                )
        if position == "user_rename":
            await controller.rename(record.id, "User title")
        before = (await _saved(backend, record.id)).model_dump()
        before_app_calls = list(app_calls)
        before_hook_calls = list(hook_calls)
        puts = len(backend.control.received)
        live["value"] = "later live input"
        title_result.set_result("Delayed title")
        await asyncio.wait_for(task, timeout=5)
        after = (await _saved(backend, record.id)).model_dump()
        renamed = position == "user_rename"
        expected_title = "User title" if renamed else "Delayed title"
        assert after.pop("title") == expected_title
        assert after.pop("title_source") == ("user" if renamed else "llm")
        before.pop("title")
        before.pop("title_source")
        assert after == before, (
            "Retitle changed durable checkpoint state or inherited pins"
        )
        assert app_calls == before_app_calls
        assert hook_calls == before_hook_calls
        assert len(backend.control.received) == puts + (0 if renamed else 1)
        assert (await backend.reader.list(part()))[0].title == expected_title
    finally:
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
