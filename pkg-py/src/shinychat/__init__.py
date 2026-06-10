from ._attachments import Attachment, attachment_to_content
from ._chat import Chat, chat_greeting, chat_ui
from ._chat_normalize import message_content, message_content_chunk
from ._markdown_stream import MarkdownStream, output_markdown_stream

__all__ = [
    "Attachment",
    "attachment_to_content",
    "Chat",
    "chat_greeting",
    "chat_ui",
    "MarkdownStream",
    "output_markdown_stream",
    "message_content",
    "message_content_chunk",
]

# Must come after the public symbols above. _input_handler imports shiny, whose
# shiny.ui._chat imports Chat/chat_ui back from this module; if this ran before
# those names were bound, that back-import would raise ImportError.
from . import _input_handler as _input_handler  # noqa: F401, I001  (deferred: registers input handler; must stay below)
