"""MCP Console ``send`` display translation.

Console's ``send`` tool echoes display facts (``{note, language}``) in
result ``_meta``, forwarded verbatim by MCP clients (chatlas, mcptools)
into ``extra``. The payload is semantic facts; shinychat owns all
presentation. Contract:
https://github.com/posit-dev/mcp-console/blob/main/docs/API.md
"""

from __future__ import annotations

import html
import re
import warnings
from typing import TYPE_CHECKING, Any

from htmltools import Tag, tags

if TYPE_CHECKING:
    from chatlas.types import ContentToolRequest

__all__ = [
    "console_send_display",
]

CONSOLE_SEND_META_KEY = "posit.mcp-console/send"


def console_send_display(
    extra: dict[str, Any], request: "ContentToolRequest"
) -> "dict[str, Any] | None":
    # Translate Console's `send` facts into the display convention when the
    # app author has not set `display`. Malformed payloads warn and
    # degrade — `_meta` is an external trust boundary. Returns a plain
    # dict (like pkg-r's list) for `get_tool_result_display` to coerce.
    # Keep in sync with pkg-r's `console_send.R`.
    facts = extra.get(CONSOLE_SEND_META_KEY)
    if facts is None:
        return None
    if not isinstance(facts, dict):
        warnings.warn(
            f"Ignoring malformed {CONSOLE_SEND_META_KEY!r} metadata: "
            f"expected a dict, not {type(facts).__name__}."
        )
        return None
    note = facts.get("note")
    if note is not None and not isinstance(note, str):
        warnings.warn(
            f"Ignoring non-string 'note' in {CONSOLE_SEND_META_KEY!r} metadata."
        )
        note = None
    language = facts.get("language")
    if language is not None and not isinstance(language, str):
        warnings.warn(
            f"Ignoring non-string 'language' in {CONSOLE_SEND_META_KEY!r} metadata."
        )
        language = None
    title = console_note_title(note)
    if title is None and language is not None:
        title = CONSOLE_LANGUAGE_NAMES.get(language)
    if title is None:
        return None
    code_tag = console_code_details(language, request)
    details = None
    if code_tag is not None:
        # Tag content implies the HTML flavor (not Markdown).
        details = {"content": code_tag, "summary": "Code"}
    return {
        # Titles render as raw HTML; the note is model-controlled text and
        # must not become markup. quote=False: a title has no attribute
        # context, and quotes read better literal.
        "title": html.escape(title, quote=False),
        "icon": CONSOLE_LANGUAGE_ICONS.get(language)
        if language is not None
        else None,
        "open_style": "framed",
        # The raw JSON argument dump is a poor fit for `send`'s argument
        # shape (note + one of r/python/sql + session fields); the executed
        # code lives in the details slot instead.
        "show_request": False,
        "details": details,
        "full_screen": True,
    }


def console_code_details(
    language: Any, request: "ContentToolRequest"
) -> "Tag | None":
    # The `language` fact names the `send` argument holding the executed
    # code; read it from the request, which the client already has, rather
    # than echoing code in `_meta`. Restricted to known languages — the
    # fact is server-controlled and becomes an HTML class attribute.
    if language not in CONSOLE_LANGUAGE_NAMES:
        return None
    arguments = getattr(request, "arguments", None)
    if not isinstance(arguments, dict):
        return None
    code = arguments.get(language)
    if not isinstance(code, str):
        return None
    # Trailing blank lines are invisible in the editor where the model
    # wrote the code but render as dead space at the foot of the block.
    code = code.rstrip()
    return tags.pre(tags.code(code, class_=f"language-{language}"))


def console_note_title(note: Any) -> "str | None":
    # A card title from Console's free-form `note`: the first contentful
    # line, minus a redundant language label. None when nothing usable
    # remains, so the caller falls back to the language name.
    if not isinstance(note, str):
        return None
    for line in note.split("\n"):
        title = console_strip_language_label(line.strip(" \t\r\f\v"))
        if title:
            return title
    return None


def console_strip_language_label(line: str) -> str:
    stripped = CONSOLE_NOTE_LANGUAGE_PREFIX.sub("", line)
    # The label's remainder was written mid-sentence; standalone, it reads
    # better capitalized. Unstripped lines stay verbatim.
    if stripped != line:
        stripped = stripped[:1].upper() + stripped[1:]
    return stripped


# Models like to prefix notes with a "<language> <noun>:" label ("R code:",
# "Python plots:"); the card already carries a language icon, so the title
# drops the redundant label. Deliberately narrow — a noun without a
# following colon ("R code review") is prose, not a label. Keep in sync
# with pkg-r's `console_strip_language_label`.
CONSOLE_NOTE_LANGUAGE_PREFIX = re.compile(
    r"^(?:R|Python|SQL)\s+(?:code|plots?|scripts?|cells?|chunks?|output)\s*[:\-–—]\s*",
    re.IGNORECASE,
)

CONSOLE_LANGUAGE_NAMES = {"r": "R", "python": "Python", "sql": "SQL"}

# Single-path language marks (Simple Icons R/Python, CC0; Bootstrap Icons
# database, MIT — the family shinychat already vendors via bsicons).
# `currentColor` inherits the row's muted glyph color and its error tint.
# Byte-identical with pkg-r's map. Keep in sync.
CONSOLE_LANGUAGE_ICONS = {
    "r": '<svg fill="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path d="M12 2.746c-6.627 0-12 3.599-12 8.037 0 3.897 4.144 7.144 9.64 7.88V16.26c-2.924-.915-4.925-2.755-4.925-4.877 0-3.035 4.084-5.494 9.12-5.494 5.038 0 8.757 1.683 8.757 5.494 0 1.976-.999 3.379-2.662 4.272.09.066.174.128.258.216.169.149.25.363.372.544 2.128-1.45 3.44-3.437 3.44-5.631 0-4.44-5.373-8.038-12-8.038zm-2.111 4.99v13.516l4.093-.002-.002-5.291h1.1c.225 0 .321.066.549.25.272.22.715.982.715.982l2.164 4.063 4.627-.002-2.864-4.826s-.086-.193-.265-.383a2.22 2.22 0 00-.582-.416c-.422-.214-1.149-.434-1.149-.434s3.578-.264 3.578-3.826c0-3.562-3.744-3.63-3.744-3.63zm4.127 2.93l2.478.002s1.149-.062 1.149 1.127c0 1.165-1.149 1.17-1.149 1.17h-2.478zm1.754 6.119c-.494.049-1.012.079-1.54.088v1.807a16.622 16.622 0 002.37-.473l-.471-.891s-.108-.183-.248-.394c-.039-.054-.08-.098-.111-.137z"/></svg>',
    "python": '<svg fill="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path d="M14.25.18l.9.2.73.26.59.3.45.32.34.34.25.34.16.33.1.3.04.26.02.2-.01.13V8.5l-.05.63-.13.55-.21.46-.26.38-.3.31-.33.25-.35.19-.35.14-.33.1-.3.07-.26.04-.21.02H8.77l-.69.05-.59.14-.5.22-.41.27-.33.32-.27.35-.2.36-.15.37-.1.35-.07.32-.04.27-.02.21v3.06H3.17l-.21-.03-.28-.07-.32-.12-.35-.18-.36-.26-.36-.36-.35-.46-.32-.59-.28-.73-.21-.88-.14-1.05-.05-1.23.06-1.22.16-1.04.24-.87.32-.71.36-.57.4-.44.42-.33.42-.24.4-.16.36-.1.32-.05.24-.01h.16l.06.01h8.16v-.83H6.18l-.01-2.75-.02-.37.05-.34.11-.31.17-.28.25-.26.31-.23.38-.2.44-.18.51-.15.58-.12.64-.1.71-.06.77-.04.84-.02 1.27.05zm-6.3 1.98l-.23.33-.08.41.08.41.23.34.33.22.41.09.41-.09.33-.22.23-.34.08-.41-.08-.41-.23-.33-.33-.22-.41-.09-.41.09zm13.09 3.95l.28.06.32.12.35.18.36.27.36.35.35.47.32.59.28.73.21.88.14 1.04.05 1.23-.06 1.23-.16 1.04-.24.86-.32.71-.36.57-.4.45-.42.33-.42.24-.4.16-.36.09-.32.05-.24.02-.16-.01h-8.22v.82h5.84l.01 2.76.02.36-.05.34-.11.31-.17.29-.25.25-.31.24-.38.2-.44.17-.51.15-.58.13-.64.09-.71.07-.77.04-.84.01-1.27-.04-1.07-.14-.9-.2-.73-.25-.59-.3-.45-.33-.34-.34-.25-.34-.16-.33-.1-.3-.04-.25-.02-.2.01-.13v-5.34l.05-.64.13-.54.21-.46.26-.38.3-.32.33-.24.35-.2.35-.14.33-.1.3-.06.26-.04.21-.02.13-.01h5.84l.69-.05.59-.14.5-.21.41-.28.33-.32.27-.35.2-.36.15-.36.1-.35.07-.32.04-.28.02-.21V6.07h2.09l.14.01zm-6.47 14.25l-.23.33-.08.41.08.41.23.33.33.23.41.08.41-.08.33-.23.23-.33.08-.41-.08-.41-.23-.33-.33-.23-.41-.08-.41.08z"/></svg>',
    "sql": '<svg xmlns="http://www.w3.org/2000/svg" fill="currentColor" viewBox="0 0 16 16"><path d="M4.318 2.687C5.234 2.271 6.536 2 8 2s2.766.27 3.682.687C12.644 3.125 13 3.627 13 4c0 .374-.356.875-1.318 1.313C10.766 5.729 9.464 6 8 6s-2.766-.27-3.682-.687C3.356 4.875 3 4.373 3 4c0-.374.356-.875 1.318-1.313M13 5.698V7c0 .374-.356.875-1.318 1.313C10.766 8.729 9.464 9 8 9s-2.766-.27-3.682-.687C3.356 7.875 3 7.373 3 7V5.698c.271.202.58.378.904.525C4.978 6.711 6.427 7 8 7s3.022-.289 4.096-.777A5 5 0 0 0 13 5.698M14 4c0-1.007-.875-1.755-1.904-2.223C11.022 1.289 9.573 1 8 1s-3.022.289-4.096.777C2.875 2.245 2 2.993 2 4v9c0 1.007.875 1.755 1.904 2.223C4.978 15.71 6.427 16 8 16s3.022-.289 4.096-.777C13.125 14.755 14 14.007 14 13zm-1 4.698V10c0 .374-.356.875-1.318 1.313C10.766 11.729 9.464 12 8 12s-2.766-.27-3.682-.687C3.356 10.875 3 10.373 3 10V8.698c.271.202.58.378.904.525C4.978 9.71 6.427 10 8 10s3.022-.289 4.096-.777A5 5 0 0 0 13 8.698m0 3V13c0 .374-.356.875-1.318 1.313C10.766 14.729 9.464 15 8 15s-2.766-.27-3.682-.687C3.356 13.875 3 13.373 3 13v-1.302c.271.202.58.378.904.525C4.978 12.71 6.427 13 8 13s3.022-.289 4.096-.777c.324-.147.633-.323.904-.525"/></svg>',
}
