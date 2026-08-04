from __future__ import annotations

from typing import Any, cast

import pytest
from shiny import Session
from shinychat._chat_types import StoredMessage
from shinychat._html_trust import record_sent_action
from shinychat._input_handler import messages_input_value


class _MockSession:
    id: str = "mock-session"


def test_messages_handler_deserializes_snapshot():
    payload = [
        {"role": "user", "segments": [{"content": "hi", "content_type": "markdown"}]},
        {
            "role": "assistant",
            "segments": [{"content": "yo", "content_type": "markdown"}],
            "htmlDeps": [{"name": "w", "version": "1.0.0"}],
        },
    ]
    dep: dict[str, object] = {"name": "w", "version": "1.0.0"}
    session = cast(Session, _MockSession())
    record_sent_action(
        session,
        "chat",
        cast(Any, {"type": "message", "message": {"role": "assistant", "segments": []}}),
        [dep],
    )

    out = messages_input_value(payload, session)
    assert all(isinstance(m, StoredMessage) for m in out)
    assert out[0].role == "user"
    assert out[1].segments[0].html_deps == [dep]


def test_messages_handler_drops_deps_the_server_never_sent():
    # See _html_trust.py: a reported dependency contributes only its identity,
    # and one the server has no record of sending is not replayable at all.
    payload = [
        {
            "role": "assistant",
            "segments": [{"content": "yo", "content_type": "markdown"}],
            "htmlDeps": [{"name": "w", "version": "1.0.0"}],
        },
    ]
    out = messages_input_value(payload, cast(Session, _MockSession()))
    assert out[0].segments[0].html_deps is None


def test_messages_handler_raises_on_message_missing_content_type():
    payload = [
        {"role": "user", "segments": [{"content": "hi"}]},
        {"role": "assistant", "segments": [{"content": "yo", "content_type": "markdown"}]},
    ]
    with pytest.raises(KeyError):
        messages_input_value(payload)


def test_messages_handler_raises_on_message_with_invalid_role():
    payload = [
        {"role": "bogus", "segments": [{"content": "hi", "content_type": "markdown"}]},
        {"role": "user", "segments": [{"content": "yo", "content_type": "markdown"}]},
    ]
    with pytest.raises(ValueError):
        messages_input_value(payload)


def test_messages_handler_raises_on_message_with_unsupported_attachment_mime():
    payload = [
        {
            "role": "user",
            "segments": [{"content": "hi", "content_type": "markdown"}],
            "attachments": [
                {
                    "mime": "application/octet-stream",
                    "data_url": "data:application/octet-stream;base64,AA==",
                    "name": "x.bin",
                    "size": 1,
                }
            ],
        },
        {"role": "assistant", "segments": [{"content": "yo", "content_type": "markdown"}]},
    ]
    with pytest.raises(ValueError):
        messages_input_value(payload)


def test_messages_handler_raises_on_message_with_oversized_attachment(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("SHINYCHAT_MAX_ATTACHMENT_SIZE", "3")
    payload = [
        {
            "role": "user",
            "segments": [{"content": "hi", "content_type": "markdown"}],
            "attachments": [
                {
                    "mime": "text/plain",
                    "data_url": "data:text/plain;base64,AQIDBA==",
                    "name": "x.txt",
                    # Spoofed smaller size should not bypass server-side enforcement.
                    "size": 1,
                }
            ],
        },
    ]
    with pytest.raises(ValueError):
        messages_input_value(payload)
