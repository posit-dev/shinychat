from typing import Any, Callable, cast

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
