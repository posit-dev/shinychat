from __future__ import annotations

import copy
import inspect
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Literal,
)

if TYPE_CHECKING:
    import chatlas
    from htmltools import HTML, Tag, TagList
    from shiny import Session

    from ._chat import Chat
    from ._chat_types import ChatGreeting, ChatMessageDict


class ChatClient:
    """
    Wraps a chatlas client bound to a :class:`~shinychat.Chat` instance.

    This class is created automatically when you pass a ``client=`` argument to
    :class:`~shinychat.Chat`. It holds the current client, handles deferred swaps
    during streaming, and wires up bookmarking.
    """

    def __init__(
        self,
        *,
        chat: "Chat",
        client: "chatlas.Chat[Any, Any]",
    ) -> None:
        self._chat = chat
        self._client = client
        # (new_client, sync) stored when a swap is requested mid-stream
        self._pending_swap: tuple["chatlas.Chat[Any, Any]", bool] | None = None
        self._cancel_bookmarking: Any = None

    @property
    def value(self) -> "chatlas.Chat[Any, Any]":
        """The underlying chatlas client."""
        return self._client

    def set(
        self,
        new_client: "chatlas.Chat[Any, Any]",
        *,
        sync: bool = True,
    ) -> None:
        """
        Replace the chatlas client.

        If a response stream is currently running the swap is deferred until
        the stream completes.

        Parameters
        ----------
        new_client
            The replacement chatlas client.
        sync
            When ``True`` (the default), copies turns, system_prompt, and tools
            from the old client to the new one before swapping.
        """
        status = self._chat.latest_message_stream.status()
        if status == "running":
            self._pending_swap = (new_client, sync)
        else:
            self._swap_client(new_client, sync=sync)

    def _swap_client(
        self,
        new_client: "chatlas.Chat[Any, Any]",
        *,
        sync: bool,
    ) -> None:
        """Perform the actual client replacement."""
        if sync:
            old = self._client
            new_client.set_turns(old.get_turns())
            old_sp = old.system_prompt
            if old_sp is not None:
                new_client.system_prompt = old_sp
            # get_tools() returns list[Tool | ToolBuiltIn]; set_tools() accepts
            # list[Callable | Tool] — the types overlap at runtime even though
            # pyright can't prove it through the invariant list parameter.
            new_client.set_tools(old.get_tools())  # type: ignore[arg-type]

        self._client = new_client

    async def clear(
        self,
        *,
        messages: "list[ChatMessageDict] | None" = None,
        greeting: bool = False,
        client_history: Literal["clear", "set", "append", "keep"] = "clear",
    ) -> None:
        """
        Clear chat messages and optionally reset the client's turn history.

        Parameters
        ----------
        messages
            A list of messages to set or append on the client. Required when
            ``client_history`` is ``"set"`` or ``"append"``, and not allowed
            with ``"clear"`` or ``"keep"``.
        greeting
            Passed to :meth:`~shinychat.Chat.clear_messages`.
        client_history
            How to handle the client's turn history:

            * ``"clear"`` (default): removes all turns from the client.
            * ``"set"``: sets the client's turns to ``messages``.  Requires
              ``messages`` to be provided.
            * ``"append"``: appends ``messages`` to the client's existing turns.
              Requires ``messages`` to be provided.
            * ``"keep"``: leaves the client's turns untouched.

        Raises
        ------
        shiny.types.NotifyException
            If an assistant response is currently streaming. To avoid this
            error, guard the call by checking
            ``chat.latest_message_stream.status() != "running"`` before calling
            :meth:`clear`. The notification message is shown without
            sanitization because it is a fixed, user-safe string.
        """
        valid_history = ("clear", "set", "append", "keep")
        if client_history not in valid_history:
            raise ValueError(
                f"`client_history={client_history!r}` is not valid. Expected "
                'one of "clear", "set", "append", or "keep".'
            )
        if client_history in ("set", "append") and messages is None:
            raise ValueError(
                f"`messages` must be provided when `client_history='{client_history}'`."
            )
        if client_history in ("clear", "keep") and messages is not None:
            raise ValueError(
                '`messages` is only valid with `client_history="set"` or '
                '`client_history="append"`.'
            )
        if self._chat.latest_message_stream.status() == "running":
            from shiny.types import NotifyException

            raise NotifyException(
                "Can't modify chat history while a response is still being "
                "generated. Please wait for it to finish or stop it first.",
                sanitize=False,
            )

        await self._chat.clear_messages(greeting=greeting)

        if messages is not None:
            for msg in messages:
                await self._chat.append_message(msg)

        if client_history == "clear":
            self._client.set_turns([])
        elif client_history == "set":
            assert messages is not None
            turns = messages_to_turns(messages)
            self._client.set_turns(turns)
        elif client_history == "append":
            assert messages is not None
            turns = self._client.get_turns() + messages_to_turns(messages)
            self._client.set_turns(turns)
        # "keep" → do nothing


def messages_to_turns(
    messages: "list[ChatMessageDict]",
) -> "list[chatlas.Turn[Any]]":
    """
    Convert a list of :class:`~shinychat.types.ChatMessageDict` dicts to
    a list of :class:`chatlas.Turn` objects.
    """
    from chatlas import Turn

    turns: list[Any] = []
    for msg in messages:
        role = msg.get("role", "assistant")
        content = msg.get("content", "")
        turns.append(Turn(content, role=role))
    return turns


def setup_greeting(
    chat: "Chat",
    greeting: "str | HTML | Tag | TagList | ChatGreeting | Callable[..., Any] | None",
    session: "Session",
) -> None:
    if greeting is None:
        return

    from htmltools import HTML, Tag, TagList
    from shiny import reactive
    from shiny.session import session_context

    from ._chat_types import ChatGreeting

    with session_context(session):

        @reactive.effect
        @reactive.event(session.input[f"{chat.id}_greeting_requested"])
        async def _on_greeting_requested() -> None:
            if isinstance(greeting, (str, HTML, Tag, TagList, ChatGreeting)):
                return await chat.set_greeting(greeting)

            sig = inspect.signature(greeting)
            if "client" in sig.parameters and chat.client is not None:
                client_copy = copy.deepcopy(chat.client.value)
                client_copy.set_turns([])
                result = greeting(client=client_copy)
            else:
                result = greeting()

            if inspect.isawaitable(result):
                result = await result

            await chat.set_greeting(result)  # type: ignore[arg-type]

    chat._effects.append(_on_greeting_requested)
