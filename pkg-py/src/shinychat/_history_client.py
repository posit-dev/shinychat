from __future__ import annotations

import warnings
from collections import deque
from collections.abc import Mapping, Sequence, Set
from typing import Any, Protocol, cast, runtime_checkable

from ._chat_bookmark import is_chatlas_chat_client, serialize_chatlas_turn
from ._chat_client import ChatClient
from ._chat_normalize import normalize_message
from ._chat_types import ChatMessage, Role
from ._history_types import TurnDict


def _validate_mapping_keys(value: Any) -> None:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            if not isinstance(key, str):
                raise ValueError(
                    "Non-string mapping key in turn data; "
                    "JSON object keys must already be strings."
                )
            _validate_mapping_keys(nested)
    elif isinstance(value, (str, bytes)):
        return
    elif isinstance(value, (Sequence, Set, deque)):
        for nested in value:
            _validate_mapping_keys(nested)


def _serialize_model_turn(turn: Any) -> dict[str, Any]:
    try:
        python_dump = turn.model_dump(mode="python")
    except TypeError:
        return turn.model_dump(mode="json")
    _validate_mapping_keys(python_dump)
    return turn.model_dump(mode="json")


@runtime_checkable
class ClientWithTurns(Protocol):
    """
    Turn-level client protocol for chat history.

    `get_turns()` must return JSON-serializable dicts (or objects with a
    `model_dump(mode="json")`); `set_turns()` must accept what `get_turns()`
    returned after a JSON round trip.

    A client that also exposes a writable `system_prompt` must treat an
    empty string as no system prompt. History normalizes a None prompt to
    that clear marker; generic clients receive it unchanged on restore.
    """

    def get_turns(self) -> list[Any]: ...
    def set_turns(self, turns: list[Any]) -> None: ...


class TurnsAdapter:
    """Normalizes a client to JSON-dict turns + client_info."""

    def __init__(self, client: ClientWithTurns | ChatClient):
        self._client: ClientWithTurns | ChatClient = client

    def _turns_client(self) -> ClientWithTurns:
        """Unwrap ChatClient to its live underlying client, so swaps propagate."""
        if isinstance(self._client, ChatClient):
            return self._client.value
        return self._client

    def get_turns_json(
        self, *, include_system_prompt: bool = False
    ) -> list[TurnDict]:
        raw = self._turns_client()
        if is_chatlas_chat_client(raw):
            turns = raw.get_turns(include_system_prompt=include_system_prompt)
            serialized: list[dict[str, Any]] = []
            for turn in turns:
                _validate_mapping_keys(turn.model_dump(mode="python"))
                serialized.append(serialize_chatlas_turn(turn))
            return cast(list[TurnDict], serialized)
        turns = raw.get_turns()
        serialized = []
        for turn in turns:
            if hasattr(turn, "model_dump"):
                serialized.append(_serialize_model_turn(turn))
            else:
                serialized.append(turn)
        return cast(list[TurnDict], serialized)

    def is_chatlas(self) -> bool:
        return is_chatlas_chat_client(self._turns_client())

    def has_system_prompt(self) -> bool:
        return hasattr(self._turns_client(), "system_prompt")

    def get_system_prompt(self) -> str | None:
        return self._turns_client().system_prompt  # type: ignore[attr-defined]

    def set_system_prompt(self, prompt: str | None) -> None:
        raw = self._turns_client()
        if is_chatlas_chat_client(raw) and prompt == "":
            # Chatlas's None API removes the system turn; an empty string
            # creates a system turn instead. Generic clients keep the string.
            prompt = None
        raw.system_prompt = prompt  # type: ignore[attr-defined]

    def get_turns_grouped(self) -> list[list[TurnDict]]:
        turns = self.get_turns_json()
        if not is_chatlas_chat_client(self._turns_client()):
            return [[t] for t in turns]
        return _group_chatlas_turns(turns)

    def set_turns_json(self, turns: list[TurnDict]) -> None:
        raw = self._turns_client()
        if is_chatlas_chat_client(raw):
            from chatlas import Turn

            raw.set_turns([Turn.model_validate(t) for t in turns])
        else:
            raw.set_turns(list(turns))

    def client_info(self) -> dict[str, str]:
        raw = self._turns_client()
        if not is_chatlas_chat_client(raw):
            return {}
        provider = raw.provider
        return {"provider": provider.name, "model": provider.model}


def is_tool_result_turn(turn: TurnDict) -> bool:
    contents = turn.get("contents")
    return (
        turn.get("role") == "user"
        and isinstance(contents, list)
        and bool(contents)
        and all(
            isinstance(c, dict) and c.get("content_type") == "tool_result"
            for c in contents
        )
    )


def _group_chatlas_turns(
    turns: list[TurnDict],
) -> list[list[TurnDict]]:
    groups: list[list[TurnDict]] = []
    i = 0
    while i < len(turns):
        t = turns[i]
        if is_tool_result_turn(t):
            if groups:
                groups[-1].append(t)
            else:
                groups.append([t])
            i += 1
        elif t.get("role") == "user":
            groups.append([t])
            i += 1
        else:
            group: list[TurnDict] = [t]
            i += 1
            while i < len(turns):
                nt = turns[i]
                if is_tool_result_turn(nt) or nt.get("role") == "assistant":
                    group.append(nt)
                    i += 1
                else:
                    break
            groups.append(group)
    return groups


def as_turns_adapter(client: Any) -> TurnsAdapter:
    """
    Wrap *client* in a :class:`TurnsAdapter`.

    Accepts a ``chatlas.Chat`` instance, a ``ChatClient`` wrapper, or any
    object that satisfies :class:`ClientWithTurns` (has ``get_turns()`` /
    ``set_turns()``).

    Raises :exc:`ValueError` for objects that lack turn-level access.
    """
    raw = getattr(client, "value", client)
    if isinstance(raw, ClientWithTurns):
        return TurnsAdapter(client)
    raise ValueError(
        "Chat history requires a client with turn-level access: either a "
        "chatlas.Chat, or an object with `get_turns() -> list` returning "
        "JSON-serializable turns and `set_turns(turns)` accepting them back."
    )


def turn_fallback_markdown(turn: TurnDict) -> str:
    """Lossy turn -> markdown used when a node has no `ui` render cache."""
    contents = turn.get("contents")
    if isinstance(contents, list):
        return "".join(
            c.get("text", "")
            for c in contents
            if isinstance(c, dict) and c.get("content_type") == "text"
        )
    return str(turn.get("content", ""))


def turn_dict_effective_role(turn: TurnDict) -> Role:
    """The UI role of a serialized turn dict.

    A user-role turn that carries only tool results displays as assistant.
    """
    if is_tool_result_turn(turn):
        return "assistant"
    role = turn.get("role")
    return role if role in ("user", "assistant", "system") else "assistant"


def _turn_group_text_fallback(group: list[TurnDict]) -> ChatMessage:
    """A text-only message for a turn group that cannot be normalized.

    Falls back to the group's last turn as plain text so replay stays
    alive instead of dropping the exchange.
    """
    last = group[-1]
    return ChatMessage(
        content=turn_fallback_markdown(last),
        role=turn_dict_effective_role(last),
    )


def normalize_turn_group(group: list[TurnDict]) -> ChatMessage | None:
    """Merge one history turn group into a single :class:`ChatMessage`.

    chatlas groups are validated back into ``chatlas.Turn`` objects, merged,
    and run through ``normalize_message`` so structured blocks, ``parts``
    interleaving, and per-block deps are reconstructed. Generic dict turns
    normalize as plain markdown. Returns ``None`` when the group has
    nothing to display.
    """
    if not group:
        return None
    if all(isinstance(t.get("contents"), list) for t in group):
        try:
            from chatlas import Turn
        except ImportError:
            return _turn_group_text_fallback(group)
        try:
            turns = [Turn.model_validate(t) for t in group]
            contents = [c for turn in turns for c in turn.contents]
            merged = Turn(role=turns[0].role, contents=contents)
            msg = normalize_message(merged)
        except Exception as e:
            warnings.warn(
                "Could not re-derive chat UI from a stored turn group "
                f"({type(e).__name__}: {e}); falling back to its text "
                "content only.",
                stacklevel=2,
            )
            return _turn_group_text_fallback(group)
        if not msg.content and not msg.blocks:
            return None
        return msg
    content = "\n\n".join(
        text for t in group if (text := str(t.get("content", "")))
    )
    if not content:
        return None
    return ChatMessage(content=content, role=turn_dict_effective_role(group[0]))
