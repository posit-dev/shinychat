from .._chat import ChatMessage, ChatMessageDict
from .._chat_client import ChatClient
from .._chat_types import ChatGreeting

try:
    from .._chat_normalize_chatlas import ToolResultDisplay

    ToolResultDisplay.model_rebuild()
except ImportError:

    class MockToolResultDisplay:
        def __init__(self, *args, **kwargs):
            raise ImportError(
                "ToolResultDisplay requires the 'chatlas' package to be installed."
            )

    ToolResultDisplay = MockToolResultDisplay


__all__ = [
    "ChatClient",
    "ChatGreeting",
    "ChatMessage",
    "ChatMessageDict",
    "ToolResultDisplay",
]
