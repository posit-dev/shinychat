from __future__ import annotations

import copy
import inspect
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Literal,
    Optional,
)

from htmltools import HTML, Tag, TagList

from ._chat import Chat, chat_ui
from ._chat_bookmark import CancelCallback
from ._chat_types import ChatGreeting, ChatMessageDict

if TYPE_CHECKING:
    import chatlas
    from htmltools import Tagified
    from shiny.session import Session

__all__ = (
    "ChatAutoServer",
    "chat_auto_ui",
    "chat_auto_server",
)


class ChatAutoServer:
    """
    A convenience wrapper that wires a :class:`~shinychat.Chat` instance to a chatlas
    client.

    This class is normally created via :func:`~shinychat.chat_auto_server` rather than
    instantiated directly.  It exposes the same surface as :class:`~shinychat.Chat` for
    reading messages and updating the UI, while adding higher-level helpers for
    swapping the underlying chatlas client and clearing the conversation.

    Parameters
    ----------
    chat
        The underlying :class:`~shinychat.Chat` (or :class:`~shinychat.ChatExpress`)
        instance.
    client
        A chatlas ``Chat`` client used for response generation.
    tag
        Optional tag returned by :meth:`tagify` (used in Express).
    bookmark_on
        Passed through to :meth:`~shinychat.Chat.enable_bookmarking`.
    """

    def __init__(
        self,
        *,
        chat: Chat,
        client: "chatlas.Chat[Any, Any]",
        tag: Tag | None = None,
        bookmark_on: Optional[Literal["response"]] = "response",
    ) -> None:
        self._chat = chat
        self._client = client
        self._tag = tag
        self._bookmark_on: Optional[Literal["response"]] = bookmark_on
        self._pending_swap: "tuple[chatlas.Chat[Any, Any], bool] | None" = None
        self._cancel_bookmarking: CancelCallback | None = None

    # ------------------------------------------------------------------
    # Express rendering
    # ------------------------------------------------------------------

    def tagify(self) -> "Tagified":
        """Return the tag for Express rendering.

        Raises
        ------
        RuntimeError
            If no tag was provided at construction time (i.e. Core mode).
        """
        if self._tag is None:
            raise RuntimeError(
                "tagify() is only available when ChatAutoServer was created "
                "via Chat.ui_auto() in Express mode."
            )
        return self._tag.tagify()

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def chat(self) -> Chat:
        """The underlying :class:`~shinychat.Chat` instance."""
        return self._chat

    @property
    def client(self) -> "chatlas.Chat[Any, Any]":
        """The current chatlas client.

        Assigning to this property is equivalent to calling
        :meth:`set_client` with ``sync=True``.
        """
        return self._client

    @client.setter
    def client(self, new_client: "chatlas.Chat[Any, Any]") -> None:
        self.set_client(new_client, sync=True)

    # ------------------------------------------------------------------
    # Module-specific
    # ------------------------------------------------------------------

    def set_client(
        self,
        new_client: "chatlas.Chat[Any, Any]",
        *,
        sync: bool = True,
    ) -> None:
        """Replace the chatlas client.

        Parameters
        ----------
        new_client
            The new chatlas ``Chat`` client to use.
        sync
            If ``True`` (the default), copy the current client's turns, system
            prompt, and tools to the new client before swapping.
        """
        if self._chat.latest_message_stream.status() == "running":
            self._pending_swap = (new_client, sync)
        else:
            self._swap_client(new_client, sync=sync)

    def _swap_client(
        self,
        new_client: "chatlas.Chat[Any, Any]",
        *,
        sync: bool,
    ) -> None:
        if sync:
            old = self._client
            new_client.set_turns(old.get_turns())
            if old.system_prompt is not None:
                new_client.system_prompt = old.system_prompt
            # chatlas get_tools() returns Tool|ToolBuiltIn but set_tools() doesn't accept ToolBuiltIn
            new_client.set_tools(old.get_tools())  # type: ignore[arg-type]

        self._client = new_client

        # Re-register bookmarking with the new client
        if self._cancel_bookmarking is not None:
            self._cancel_bookmarking()
            self._cancel_bookmarking = None
        cancel = self._chat.enable_bookmarking(
            new_client, bookmark_on=self._bookmark_on
        )
        self._cancel_bookmarking = cancel

    async def clear(
        self,
        *,
        messages: list[ChatMessageDict] | None = None,
        greeting: bool = False,
        client_history: Literal["clear", "set", "append", "keep"] = "clear",
    ) -> None:
        """Clear the chat UI and manage client history.

        Parameters
        ----------
        messages
            Optional list of message dicts to display in the chat after clearing.
        greeting
            If ``True``, also clear the greeting (triggers re-request).
        client_history
            How to handle the chatlas client's turn history:

            - ``"clear"``: wipe turns.
            - ``"set"``: replace with ``messages`` (converted to turns).
            - ``"append"``: add ``messages`` to existing turns.
            - ``"keep"``: leave turns untouched.
        """
        if messages is None and client_history in ("set", "append"):
            raise ValueError(
                f"client_history='{client_history}' requires `messages` to be provided."
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
            existing = self._client.get_turns()
            extra = messages_to_turns(messages)
            self._client.set_turns(existing + extra)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def chat_auto_ui(
    id: str,
    **kwargs: Any,
) -> Tag:
    """UI container for an auto-wired chat component (Shiny Core).

    A thin wrapper around :func:`~shinychat.chat_ui` with ``enable_cancel=True``
    pre-set. All keyword arguments are forwarded to :func:`~shinychat.chat_ui`.

    Parameters
    ----------
    id
        A unique identifier for the chat UI.
    kwargs
        Keyword arguments forwarded to :func:`~shinychat.chat_ui`.
    """
    return chat_ui(
        id,
        enable_cancel=True,
        **kwargs,
    )


def chat_auto_server(
    id: str,
    client: "chatlas.Chat[Any, Any]",
    *,
    greeting: "str | HTML | Tag | TagList | ChatGreeting | Callable[..., Any] | None" = None,
    bookmark_on: Optional[Literal["response"]] = "response",
) -> ChatAutoServer:
    """Wire up a chatlas client to a chat UI with streaming, cancellation, and bookmarking.

    Creates a :class:`~shinychat.Chat`, registers handlers for user input,
    cancellation, and optional bookmarking, then returns a
    :class:`~shinychat.ChatAutoServer` that wraps it all.

    Parameters
    ----------
    id
        The chat component ID (must match the corresponding ``chat_auto_ui(id)`` call).
    client
        A chatlas ``Chat`` instance used to generate responses.
    greeting
        Optional greeting content.  Can be:

        * A static string/HTML/tag — displayed when the chat first appears.
        * A callable — called (with an optional ``client`` keyword argument) each
          time a greeting is requested; the return value is passed to
          :meth:`~shinychat.Chat.set_greeting`.
    bookmark_on
        When to trigger a bookmark.  Passed to
        :meth:`~shinychat.Chat.enable_bookmarking`.

    Returns
    -------
    :
        A :class:`~shinychat.ChatAutoServer` that exposes the wired-up chat.
    """
    from chatlas import StreamController
    from shiny import reactive
    from shiny.session import require_active_session

    session = require_active_session(None)
    chat = Chat(id)

    controller = StreamController()

    result = ChatAutoServer(
        chat=chat,
        client=client,
        bookmark_on=bookmark_on,
    )

    @chat.on_user_submit
    async def _on_user_submit(user_input: str) -> None:
        response = await result.client.stream_async(
            user_input,
            content="all",
            controller=controller,
        )
        await chat.append_message_stream(response)

    cancel_input_id = f"{id}_cancel"

    @reactive.effect
    @reactive.event(session.input[cancel_input_id])
    async def _on_cancel() -> None:
        controller.cancel()

    @reactive.effect
    async def _on_stream_complete() -> None:
        status = chat.latest_message_stream.status()
        if status == "running":
            return

        swap = result._pending_swap
        if swap is None:
            return
        result._pending_swap = None
        new_client, sync = swap
        result._swap_client(new_client, sync=sync)

    cancel_bm = chat.enable_bookmarking(client, bookmark_on=bookmark_on)
    result._cancel_bookmarking = cancel_bm

    setup_greeting(chat, result, greeting, session)

    return result


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


def messages_to_turns(
    messages: list[ChatMessageDict],
) -> list["chatlas.Turn"]:
    """Convert a list of ``ChatMessageDict`` objects to chatlas ``Turn`` objects."""
    from chatlas import Turn

    turns: list[Turn] = []
    for msg in messages:
        role_raw = msg.get("role", "assistant")
        content = msg.get("content", "")
        if role_raw == "user":
            role: Literal["user", "assistant"] = "user"
        else:
            role = "assistant"
        turns.append(Turn(content, role=role))
    return turns


def setup_greeting(
    chat: Chat,
    result: "ChatAutoServer",
    greeting: "str | HTML | Tag | TagList | ChatGreeting | Callable[..., Any] | None",
    session: "Session",
) -> None:
    """Wire up greeting handling for ``chat_auto_server``."""
    from shiny import reactive

    if greeting is None:
        return

    greeting_input_id = f"{chat.id}_greeting_requested"

    if isinstance(greeting, (str, HTML, Tag, TagList, ChatGreeting)):
        static_greeting = greeting

        @reactive.effect
        @reactive.event(session.input[greeting_input_id])
        async def _handle_static_greeting() -> None:
            await chat.set_greeting(static_greeting)

    elif callable(greeting):
        fn = greeting
        fn_params = inspect.signature(fn).parameters
        has_client_param = "client" in fn_params

        @reactive.effect
        @reactive.event(session.input[greeting_input_id])
        async def _handle_greeting() -> None:
            if has_client_param:
                greeting_client = copy.deepcopy(result.client)
                greeting_client.set_turns([])
                g = fn(client=greeting_client)
            else:
                g = fn()
            if inspect.isawaitable(g):
                g = await g
            await chat.set_greeting(g)
