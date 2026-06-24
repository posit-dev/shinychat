from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from ._chat_bookmark import is_chatlas_chat_client
from ._chat_client import ChatClient


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

    def get_turns_json(self) -> list[dict[str, Any]]:
        raw = self._turns_client()
        turns = raw.get_turns()
        if is_chatlas_chat_client(raw):
            return [t.model_dump(mode="json") for t in turns]
        return list(turns)

    def set_turns_json(self, turns: list[dict[str, Any]]) -> None:
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
