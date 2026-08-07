import shinychat  # noqa: F401
from shiny.input_handler import input_handlers


def test_messages_input_handler_is_not_registered():
    assert "shinychat.messages" not in input_handlers
