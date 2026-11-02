"""New chat is an explicit reset, not rollback to an earlier branch."""

import asyncio
from typing import Any, cast

import pytest
from test_history_controller import _FakeChat, _make_controller
from test_history_stream_persistence import (
    _assistant_message,
    _Backend,
    _chunk,
    _end_stream,
    _open_stream,
    _saved,
    _text,
)
from test_history_stream_persistence import backend as _backend_fixture

backend = _backend_fixture


async def _completed_conversation(backend: _Backend) -> tuple[Any, list[str]]:
    saves: list[str] = []
    writer, _ = _make_controller(
        store=backend.store,
        save_callbacks=[lambda values: saves.append("save")],
    )
    writer.adapter.set_turns_json([])
    transcript, _ = await _open_stream(writer)
    writer.adapter.set_turns_json(
        [
            {"role": "user", "content": "question"},
            {"role": "assistant", "content": "answer"},
        ]
    )
    await _chunk(transcript, _assistant_message(_text("answer")))
    await _end_stream(transcript)
    await writer.on_response()
    saves.clear()
    return writer, saves


@pytest.mark.anyio
@pytest.mark.parametrize("failure", ["nonfinite", "getter"])
async def test_new_chat_discards_uncapturable_model_state_and_keeps_saved_position(
    backend: _Backend,
    failure: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    writer, saves = await _completed_conversation(backend)
    record = writer._exchange_recorder.record
    assert record is not None
    saved_before = (await _saved(backend, record.id)).model_dump_json()
    writes_before = len(backend.control.received)

    with monkeypatch.context() as patch:
        if failure == "nonfinite":
            writer.adapter.set_turns_json(
                [{"role": "assistant", "content": float("nan")}]
            )
        else:

            def unavailable() -> Any:
                raise RuntimeError("custom getter failed")

            patch.setattr(writer.adapter, "get_turns_json", unavailable)
        with pytest.warns(UserWarning, match="before New chat"):
            await writer.new_chat()

    # Failed outgoing capture does not overwrite the stored position or
    # turn the reset into an application-values capture.
    assert len(backend.control.received) == writes_before
    assert (await _saved(backend, record.id)).model_dump_json() == saved_before
    assert saves == []
    assert writer.adapter.get_turns_json() == []
    assert writer._exchange_recorder.record is None
    assert writer._active_id_now() is None
    assert cast(_FakeChat, writer.chat).clear_messages_calls == 1

    # A new accepted input has a new identity and cannot mutate the old
    # record, including when the custom store retains its argument.
    await _open_stream(writer)
    fresh = writer._exchange_recorder.record
    assert fresh is not None and fresh.id != record.id
    assert (await _saved(backend, record.id)).model_dump_json() == saved_before


@pytest.mark.anyio
@pytest.mark.parametrize("failure", ["store", "cancelled", "fatal", "reset"])
async def test_new_chat_does_not_swallow_store_cancellation_fatal_or_reset_failures(
    backend: _Backend,
    failure: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    writer, saves = await _completed_conversation(backend)
    record = writer._exchange_recorder.record
    assert record is not None
    saved_before = await _saved(backend, record.id)
    error: BaseException
    if failure == "cancelled":
        error = asyncio.CancelledError("capture cancelled")
    elif failure == "fatal":
        error = KeyboardInterrupt("capture fatal")
    else:
        error = RuntimeError(f"{failure} failed")

    def fail(*args: Any) -> Any:
        raise error

    if failure == "store":
        backend.control.failures.append(error)
    elif failure == "reset":
        monkeypatch.setattr(writer.adapter, "set_turns_json", fail)
    else:
        monkeypatch.setattr(writer.adapter, "get_turns_json", fail)

    with pytest.raises(type(error), match=str(error)):
        await writer.new_chat()

    assert writer._exchange_recorder.record is record
    assert writer._active_id_now() == record.id
    assert cast(_FakeChat, writer.chat).clear_messages_calls == 0
    assert saves == []
    saved_after = await _saved(backend, record.id)
    assert saved_after.active_leaf == saved_before.active_leaf
    assert saved_after.nodes == saved_before.nodes
