from __future__ import annotations

import warnings

import pytest
from shinychat._chat_types import StoredMessage, StoredSegment
from shinychat._input_handler import messages_input_value


def test_messages_handler_deserializes_snapshot():
    payload = (
        {
            "role": "user",
            "segments": ({"content": "hi", "content_type": "markdown"},),
        },
        {
            "role": "assistant",
            "segments": ({"content": "yo", "content_type": "markdown"},),
            "htmlDeps": ({"name": "w", "version": "1.0.0"},),
        },
    )
    out = messages_input_value(payload)
    assert all(isinstance(m, StoredMessage) for m in out)
    assert out[0].role == "user"
    seg = out[1].segments[0]
    assert isinstance(seg, StoredSegment)
    assert seg.html_deps == [{"name": "w", "version": "1.0.0"}]

    with warnings.catch_warnings():
        warnings.simplefilter("error")
        out[1].model_dump_json()


def test_messages_handler_raises_on_message_missing_content_type():
    payload = [
        {"role": "user", "segments": [{"content": "hi"}]},
        {
            "role": "assistant",
            "segments": [{"content": "yo", "content_type": "markdown"}],
        },
    ]
    with pytest.raises(KeyError):
        messages_input_value(payload)


def test_messages_handler_raises_on_message_with_invalid_role():
    payload = [
        {
            "role": "bogus",
            "segments": [{"content": "hi", "content_type": "markdown"}],
        },
        {
            "role": "user",
            "segments": [{"content": "yo", "content_type": "markdown"}],
        },
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
        {
            "role": "assistant",
            "segments": [{"content": "yo", "content_type": "markdown"}],
        },
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
