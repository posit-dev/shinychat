from __future__ import annotations

import pytest
from shinychat._history_types import CapturedMessage
from test_history_controller import (
    _make_v2_resubmit_real_chat,
    _stored_message,
    _wire_resubmit_capture,
)


@pytest.mark.anyio
@pytest.mark.parametrize(
    "root_notice", [False, True], ids=["restored", "root-notice"]
)
async def test_resubmit_after_display_replay_keeps_the_server_parent_prefix(
    request: pytest.FixtureRequest, root_notice: bool
) -> None:
    controller, chat, _adapter, _store, _first, _target = (
        _make_v2_resubmit_real_chat(
            request, chat_id=f"replayed_resubmit_{root_notice}"
        )
    )
    record = controller._exchange_recorder.record
    assert record is not None
    if root_notice:
        record.append_message(
            record.root_id,
            CapturedMessage.from_stored_message(
                _stored_message("assistant", "startup notice"), icon=None
            ),
        )
    _wire_resubmit_capture(controller, chat)

    # Restore uses the real append pipeline with capture suspended. These
    # entries have no exchange IDs, unlike live accepted-input capture.
    await controller._replay_exchange_display(
        record, tuple(record.path_node_ids())
    )
    assert all(entry.exchange_id is None for entry in chat._transcript.read())
    prefix = (
        ["startup notice", "first", "reply one"]
        if root_notice
        else ["first", "reply one"]
    )
    assert [message["content"] for message in chat.messages()] == [
        *prefix,
        "second",
        "reply two",
    ]

    await controller.handle_edit(
        3 if root_notice else 2, "second edited", request_id="replayed-edit"
    )

    # The server-direct staged admission committed the accepted input under
    # its staged exchange ID: the transcript is the parent prefix plus the
    # admitted edit, exactly once — no browser echo involved.
    assert [message["content"] for message in chat.messages()] == [
        *prefix,
        "second edited",
    ]
    assert [
        message["segments"][0]["content"]
        for message in chat._messages_for_bookmark()
    ] == [
        *prefix,
        "second edited",
    ]
