from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from ._chat_bookmark import is_chatlas_chat_client


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

    def __init__(self, client: Any):
        self._client = client
        self._is_chatlas = is_chatlas_chat_client(client)

    def get_turns_json(self) -> list[dict[str, Any]]:
        turns = self._client.get_turns()
        if self._is_chatlas:
            return [t.model_dump(mode="json") for t in turns]
        return list(turns)

    def set_turns_json(self, turns: list[dict[str, Any]]) -> None:
        if self._is_chatlas:
            from chatlas import Turn

            self._client.set_turns([Turn.model_validate(t) for t in turns])
        else:
            self._client.set_turns(list(turns))

    def client_info(self) -> dict[str, str]:
        if not self._is_chatlas:
            return {}
        provider = self._client.provider
        return {"provider": provider.name, "model": provider.model}


def as_turns_adapter(client: Any) -> TurnsAdapter:
    """
    Wrap *client* in a :class:`TurnsAdapter`.

    Accepts a ``chatlas.Chat`` instance or any object that satisfies
    :class:`ClientWithTurns` (has ``get_turns()`` / ``set_turns()``).

    Raises :exc:`ValueError` for objects that lack turn-level access.
    """
    if isinstance(client, ClientWithTurns):
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
