from __future__ import annotations

import copy
import warnings
from typing import Any, Awaitable, Callable, Union

from ._chat_bookmark import is_chatlas_chat_client
from ._history_client import turn_fallback_markdown
from ._utils import wrap_async

TitleFn = Callable[
    [list[dict[str, Any]]], Union[str, None, Awaitable[str], Awaitable[None]]
]

TITLE_SYSTEM_PROMPT = (
    "You title chat conversations. Reply with ONLY a title for the "
    "conversation excerpt the user provides: at most 6 words, no quotes, "
    "no trailing punctuation."
)
MAX_TITLE_LEN = 80
MAX_FALLBACK_LEN = 50


async def generate_title(
    title_fn: TitleFn | None,
    client: Any,
    turns: list[dict[str, Any]],
) -> str | None:
    """
    Returns a generated title, or None on any failure (caller keeps the
    fallback title). `title_fn` wins when provided; otherwise a one-shot LLM
    call on a copy of `client` (chatlas only).
    """
    try:
        if title_fn is not None:
            title = await wrap_async(title_fn)(turns)
        else:
            title = await chatlas_one_shot_title(client, turns)
        if title is None:
            return None
        title = " ".join(str(title).split())
        return title[:MAX_TITLE_LEN] or None
    except Exception as e:
        warnings.warn(
            f"Conversation title generation failed: {e}", stacklevel=2
        )
        return None


def fallback_title(turns: list[dict[str, Any]]) -> str:
    for turn in turns:
        if turn.get("role") != "user":
            continue
        text = " ".join(turn_fallback_markdown(turn).split())
        if not text:
            continue
        if len(text) <= MAX_FALLBACK_LEN:
            return text
        return text[: MAX_FALLBACK_LEN - 3] + "..."
    return "New chat"


async def chatlas_one_shot_title(
    client: Any, turns: list[dict[str, Any]]
) -> str | None:
    if client is None or not is_chatlas_chat_client(client):
        return None
    if not turns:
        return None

    excerpt = "\n\n".join(
        f"{t.get('role', '?')}: {turn_fallback_markdown(t)[:500]}"
        for t in turns[:2]
    )
    titler = copy.deepcopy(client)
    titler.set_turns([])
    titler.set_tools([])
    titler.system_prompt = TITLE_SYSTEM_PROMPT
    response = await titler.chat_async(excerpt, echo="none")
    return await response.get_content()
