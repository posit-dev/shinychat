from __future__ import annotations

from collections import deque
from collections.abc import Mapping, Sequence, Set
from typing import Any, Protocol, runtime_checkable

from ._chat_bookmark import is_chatlas_chat_client, serialize_chatlas_turn
from ._chat_client import ChatClient


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
    ) -> list[dict[str, Any]]:
        raw = self._turns_client()
        if is_chatlas_chat_client(raw):
            turns = raw.get_turns(include_system_prompt=include_system_prompt)
            serialized: list[dict[str, Any]] = []
            for turn in turns:
                _validate_mapping_keys(turn.model_dump(mode="python"))
                serialized.append(serialize_chatlas_turn(turn))
            return serialized
        turns = raw.get_turns()
        serialized: list[dict[str, Any]] = []
        for turn in turns:
            if hasattr(turn, "model_dump"):
                serialized.append(_serialize_model_turn(turn))
            else:
                serialized.append(turn)
        return serialized

    def is_chatlas(self) -> bool:
        return is_chatlas_chat_client(self._turns_client())

    def get_turns_grouped(self) -> list[list[dict[str, Any]]]:
        turns = self.get_turns_json()
        if not is_chatlas_chat_client(self._turns_client()):
            return [[t] for t in turns]
        return _group_chatlas_turns(turns)

    def set_turns_json(
        self,
        turns: list[dict[str, Any]],
        *,
        include_system_prompt: bool = False,
    ) -> None:
        raw = self._turns_client()
        if is_chatlas_chat_client(raw):
            from chatlas import Turn

            restored = [Turn.model_validate(t) for t in turns]
            system = (
                restored[0]
                if restored and restored[0].role == "system"
                else None
            )
            conversation = restored[1:] if system is not None else restored
            if any(turn.role == "system" for turn in conversation):
                raise ValueError(
                    "System turns are only allowed at the start of history."
                )
            # chatlas keeps the system prompt separately from set_turns().
            raw.set_turns(conversation)
            if include_system_prompt or system is not None:
                raw.system_prompt = system.text if system is not None else None
        else:
            raw.set_turns(list(turns))

    def client_info(self) -> dict[str, str]:
        raw = self._turns_client()
        if not is_chatlas_chat_client(raw):
            return {}
        provider = raw.provider
        return {"provider": provider.name, "model": provider.model}


def _is_tool_result_turn(turn: dict[str, Any]) -> bool:
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
    turns: list[dict[str, Any]],
) -> list[list[dict[str, Any]]]:
    groups: list[list[dict[str, Any]]] = []
    i = 0
    while i < len(turns):
        t = turns[i]
        if _is_tool_result_turn(t):
            if groups:
                groups[-1].append(t)
            else:
                groups.append([t])
            i += 1
        elif t.get("role") == "user":
            groups.append([t])
            i += 1
        else:
            group: list[dict[str, Any]] = [t]
            i += 1
            while i < len(turns):
                nt = turns[i]
                if _is_tool_result_turn(nt) or nt.get("role") == "assistant":
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


def turn_fallback_markdown(turn: dict[str, Any]) -> str:
    """Lossy turn -> markdown used when a node has no `ui` render cache."""
    contents = turn.get("contents")
    if isinstance(contents, list):
        return "".join(
            c.get("text", "")
            for c in contents
            if isinstance(c, dict) and c.get("content_type") == "text"
        )
    return str(turn.get("content", ""))
