"""The trust boundary for html the browser reports back in its message snapshot.

The client reports its settled-message snapshot as the ``{id}_messages`` input
(see ``_input_handler.py``). Those reports get persisted -- bookmark state and
the conversation history store -- and replayed into sinks that assign raw HTML:
``RawHTML`` writes to ``innerHTML``, and the tool cards' ``icon``/``footer``/
``value`` attributes reach ``dangerouslySetInnerHTML``. Since a server bookmark
is shareable via its ``_state_id_`` URL, a forged report would otherwise be a
stored-script vector against whoever opens that URL.

So the server keeps its own ledger of what it sent and treats the client's
report as nothing more than a set of things to look up:

* html *dependencies* are substituted wholesale -- a reported dependency
  contributes only its ``name@version``, and the server's own copy is what gets
  persisted.
* html *content* is validated by string equality against the ledger. A miss
  degrades the segment to markdown, where the client escapes shinychat's
  raw-HTML element names (see ``reservedElements.ts``), so forged content
  renders as literal text rather than executing.

The browser only reports *settled* messages -- ``buildMessagesSnapshot()`` drops
anything still streaming -- so the single string we ever have to recognize is the
finished segment, with consecutive same-type chunks already concatenated by the
client. Rather than guessing where the client closes a segment, the ledger
performs the same merge and records the result when the message closes.
"""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING
from weakref import WeakKeyDictionary

from ._chat_types import ChunkAction, MessagePayloadSegment, SerializedDep

if TYPE_CHECKING:
    from shiny.session import Session

    from ._chat_types import ChatAction


class SentHtml:
    """What one session's server has sent, as far as trust is concerned."""

    def __init__(self) -> None:
        # Hashes rather than the strings themselves: validation is string
        # equality, so storing the content would only make the ledger grow with
        # the size of every payload.
        self.content_hashes: set[str] = set()
        # Segments of the message currently streaming, per chat id, merged the
        # way the client merges them.
        self.open_segments: dict[str, list[MessagePayloadSegment]] = {}
        # Keyed by `name@version`; the value is the server's own copy.
        self.deps: dict[str, SerializedDep] = {}


# Session-wide rather than per chat: `messages_input_value()` has no chat id to
# key on, and content the server sent to one chat is still server-authored html.
# Dependencies are genuinely page-wide -- they render into `document.head`, so
# one already loaded for any chat is loaded for the page.
sent_by_session: "WeakKeyDictionary[Session, SentHtml]" = WeakKeyDictionary()


def record_sent_action(
    session: "Session | None",
    chat_id: str,
    action: "ChatAction",
    html_deps: list[SerializedDep] | None = None,
) -> None:
    """Record what an outgoing ``shinyChatMessage`` makes trustworthy."""
    if session is None:
        return
    sent = sent_by_session.setdefault(session, SentHtml())

    if html_deps:
        for dep in html_deps:
            key = dep_key(dep)
            if key is not None:
                sent.deps[key] = dep

    if action["type"] == "message":
        # A one-shot message is already what the browser will report back.
        trust_segments(sent, action["message"]["segments"])
    elif action["type"] == "chunk_start":
        sent.open_segments[chat_id] = list(action["message"]["segments"])
    elif action["type"] == "chunk":
        # The client drops a chunk that isn't extending a streaming message, so a
        # chunk we never saw a chunk_start for displays nothing to trust.
        open_segments = sent.open_segments.get(chat_id)
        if open_segments is not None:
            sent.open_segments[chat_id] = merge_chunk(open_segments, action)
    elif action["type"] == "chunk_end":
        # The message has settled, so this is the report to expect.
        trust_segments(sent, sent.open_segments.pop(chat_id, []))
    # Every other action (greeting*, clear, update_input, ...) carries no message
    # content. Leaving the in-flight segments untouched matters: dropping them
    # would let an unrelated action sent mid-stream break the merge in flight.


def is_trusted_html(session: "Session | None", content: str) -> bool:
    """Did this session's server send exactly this html string?"""
    if session is None:
        return False
    sent = sent_by_session.get(session)
    return sent is not None and hash_content(content) in sent.content_hashes


def trusted_html_deps(
    session: "Session | None",
    deps: list[SerializedDep] | None,
) -> list[SerializedDep] | None:
    """Swap reported dependencies for the server's own copies, dropping the rest."""
    if session is None or not deps:
        return None
    sent = sent_by_session.get(session)
    if sent is None or not sent.deps:
        return None

    out: list[SerializedDep] = []
    seen: set[str] = set()
    for dep in deps:
        key = dep_key(dep)
        if key is None or key in seen or key not in sent.deps:
            continue
        seen.add(key)
        out.append(sent.deps[key])
    return out or None


def merge_chunk(
    segments: list[MessagePayloadSegment],
    action: ChunkAction,
) -> list[MessagePayloadSegment]:
    """Mirror the client's ``chunk`` reducer.

    A chunk extends the last segment when it shares its content type,
    ``operation="replace"`` restarts the accumulation, and an absent content type
    inherits the type already in progress.
    """
    last = segments[-1] if segments else None
    content_type = action.get("content_type")
    if content_type is None:
        content_type = last["content_type"] if last is not None else "markdown"
    content = action["content"]

    if action.get("operation") == "replace":
        return [
            MessagePayloadSegment(content=content, content_type=content_type)
        ]
    if last is not None and last["content_type"] == content_type:
        return [
            *segments[:-1],
            MessagePayloadSegment(
                content=last["content"] + content, content_type=content_type
            ),
        ]
    return [
        *segments,
        MessagePayloadSegment(content=content, content_type=content_type),
    ]


def trust_segments(
    sent: SentHtml,
    segments: list[MessagePayloadSegment],
) -> None:
    for seg in segments:
        if seg["content_type"] == "html":
            sent.content_hashes.add(hash_content(seg["content"]))


def dep_key(dep: SerializedDep) -> str | None:
    name = dep.get("name")
    version = dep.get("version")
    if not isinstance(name, str) or not isinstance(version, str):
        return None
    return f"{name}@{version}"


def hash_content(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()
