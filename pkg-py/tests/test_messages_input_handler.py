from __future__ import annotations

import logging

import pytest
from shinychat._chat_types import StoredMessage
from shinychat._input_handler import messages_input_value


def test_messages_handler_deserializes_snapshot():
    payload = [
        {"role": "user", "segments": [{"content": "hi", "content_type": "markdown"}]},
        {
            "role": "assistant",
            "segments": [{"content": "yo", "content_type": "markdown"}],
            "htmlDeps": [{"name": "w", "version": "1.0.0"}],
        },
    ]
    out = messages_input_value(payload)
    assert all(isinstance(m, StoredMessage) for m in out)
    assert out[0].role == "user"
    assert out[1].segments[0].html_deps == [{"name": "w", "version": "1.0.0"}]


def test_messages_handler_skips_message_missing_content_type():
    payload = [
        {"role": "user", "segments": [{"content": "hi"}]},
        {"role": "assistant", "segments": [{"content": "yo", "content_type": "markdown"}]},
    ]
    out = messages_input_value(payload)
    assert len(out) == 1
    assert out[0].role == "assistant"


def test_messages_handler_skips_message_with_invalid_role():
    payload = [
        {"role": "bogus", "segments": [{"content": "hi", "content_type": "markdown"}]},
        {"role": "user", "segments": [{"content": "yo", "content_type": "markdown"}]},
    ]
    out = messages_input_value(payload)
    assert len(out) == 1
    assert out[0].role == "user"


def test_messages_handler_logs_warning_on_skipped_message(
    caplog: pytest.LogCaptureFixture,
):
    payload = [{"role": "bogus", "segments": []}]
    with caplog.at_level(logging.WARNING):
        out = messages_input_value(payload)
    assert out == []
    assert len(caplog.records) == 1
    assert "malformed" in caplog.text.lower()


def test_messages_handler_skips_message_with_unsupported_attachment_mime():
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
    out = messages_input_value(payload)
    assert len(out) == 1
    assert out[0].role == "assistant"


def test_messages_handler_skips_message_with_oversized_attachment(
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
    out = messages_input_value(payload)
    assert out == []
