from typing import Any, Callable, cast

import pytest
import shinychat  # noqa: F401  (import side effect registers the handler)
from shiny.input_handler import input_handlers


def test_user_input_handler_is_registered():
    assert "shinychat.userInput" in input_handlers


def _get_handler() -> Callable[[Any, Any, Any], Any]:
    return cast(
        Callable[[Any, Any, Any], Any], input_handlers["shinychat.userInput"]
    )


def test_user_input_handler_normalizes_empty_attachments():
    handler = _get_handler()
    result = handler({"text": "hi", "attachments": []}, "chat_user_input", None)
    assert result["text"] == "hi"
    assert result["attachments"] == []


def test_user_input_handler_produces_attachment_objects():
    from shinychat._attachments import Attachment

    handler = _get_handler()
    value = {
        "text": "hello",
        "attachments": [
            {
                "mime": "image/png",
                "data_url": "data:image/png;base64,AA==",
                "name": "x.png",
                "size": 42,
            }
        ],
    }
    result = handler(value, "chat_user_input", None)
    att = result["attachments"][0]
    assert isinstance(att, Attachment)
    assert att.mime == "image/png"
    assert att.data_url == "data:image/png;base64,AA=="
    assert att.name == "x.png"
    assert att.size == 42


def test_user_input_handler_rejects_oversized_attachment_payload(
    monkeypatch: pytest.MonkeyPatch,
):
    handler = _get_handler()
    monkeypatch.setenv("SHINYCHAT_MAX_ATTACHMENT_SIZE", "3")
    value = {
        "text": "hello",
        "attachments": [
            {
                "mime": "text/plain",
                "data_url": "data:text/plain;base64,AQIDBA==",
                "name": "x.txt",
                # Spoofed smaller size should not bypass server-side enforcement.
                "size": 1,
            }
        ],
    }
    with pytest.raises(ValueError, match="maximum attachment size"):
        handler(value, "chat_user_input", None)


def test_user_input_handler_rejects_unsupported_attachment_mime():
    handler = _get_handler()
    value = {
        "text": "hello",
        "attachments": [
            {
                "mime": "application/octet-stream",
                "data_url": "data:application/octet-stream;base64,AA==",
                "name": "x.bin",
                "size": 1,
            }
        ],
    }
    with pytest.raises(ValueError, match="unsupported MIME type"):
        handler(value, "chat_user_input", None)
