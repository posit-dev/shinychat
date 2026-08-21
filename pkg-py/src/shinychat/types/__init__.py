from .._attachments import Attachment
from .._chat import ChatMessage, ChatMessageDict
from .._chat_client import ChatClient
from .._chat_types import ChatGreeting
from .._history import HistoryOptions
from .._history_store import (
    ConversationPartition,
    ConversationStore,
    FileConversationStore,
)
from .._history_types import ConversationMeta, ConversationRecord
from .._page_chat import ChatArtifact, ChatNavPanel, ChatSidebar

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
    "Attachment",
    "ChatClient",
    "ChatGreeting",
    "HistoryOptions",
    "ChatMessage",
    "ChatMessageDict",
    "ConversationMeta",
    "ConversationPartition",
    "ConversationRecord",
    "ConversationStore",
    "FileConversationStore",
    "ToolResultDisplay",
    "ChatArtifact",
    "ChatNavPanel",
    "ChatSidebar",
]
