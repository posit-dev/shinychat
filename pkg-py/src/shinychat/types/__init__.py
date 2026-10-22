from .._attachments import Attachment
from .._chat import ChatMessage, ChatMessageDict
from .._chat_client import ChatClient
from .._chat_types import ChatGreeting
from .._drawer import ChatDrawerController
from .._history import HistoryOptions
from .._history_store import (
    ConversationPartition,
    ConversationStore,
    FileConversationStore,
)
from .._history_types import (
    ConversationMeta,
    # `ConversationRecord` is the version-tracking validation/construction
    # entry point; the runtime type the controller/recorder build -- and
    # that stores receive in put() and should isinstance-check against --
    # is `ConversationRecordV2`.
    ConversationRecord,
    ConversationRecordV1,
    ConversationRecordV2,
    HistoryNavigateContext,
)
from .._page_chat import ChatDrawer, ChatNavPanel, ChatSidebar

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
    "ChatDrawerController",
    "ChatClient",
    "ChatGreeting",
    "HistoryOptions",
    "ChatMessage",
    "ChatMessageDict",
    "ConversationMeta",
    "ConversationPartition",
    "ConversationRecord",
    "ConversationRecordV1",
    "ConversationRecordV2",
    "ConversationStore",
    "FileConversationStore",
    "HistoryNavigateContext",
    "ToolResultDisplay",
    "ChatDrawer",
    "ChatNavPanel",
    "ChatSidebar",
]
