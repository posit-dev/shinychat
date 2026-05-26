from __future__ import annotations

import copy
import inspect
from typing import (
    TYPE_CHECKING,
    Any,
    AsyncIterable,
    Callable,
    Iterable,
    Literal,
    Optional,
    Union,
)

from htmltools import HTML, Tag, TagAttrValue, TagChild, TagList

from ._chat import Chat, chat_ui
from ._chat_types import (
    ChatGreeting,
    ChatMessage,
    ChatMessageDict,
)

if TYPE_CHECKING:
    import chatlas
    from shiny.ui.css import CssUnit

__all__ = (
    "chat_mod_ui",
    "chat_mod_server",
    "ChatServerState",
)


def chat_mod_ui(
    id: str,
    *,
    messages: Optional[
        Iterable[Union[str, TagChild, ChatMessageDict, ChatMessage, Any]]
    ] = None,
    placeholder: str = "Enter a message...",
    width: CssUnit = "min(680px, 100%)",
    height: CssUnit = "auto",
    fill: bool = True,
    icon_assistant: Optional[Union[HTML, Tag, TagList]] = None,
    footer: Optional[TagChild] = None,
    **kwargs: TagAttrValue,
) -> Tag:
    """
    UI for a batteries-included chat module.

    Use with :func:`~shinychat.chat_mod_server` to create a complete chat interface
    that automatically wires a chatlas client to the chat UI.

    Parameters
    ----------
    id
        The module ID. Must match the ``id`` passed to :func:`~shinychat.chat_mod_server`.
    messages
        Initial messages to display in the chat.
    placeholder
        Placeholder text for the chat input.
    width
        The width of the chat container.
    height
        The height of the chat container.
    fill
        Whether the chat should vertically take available space inside a fillable
        container.
    icon_assistant
        The icon to use for assistant chat messages.
    footer
        Optional HTML content to display below the chat input.
    kwargs
        Additional attributes for the chat container element.
    """
    from shiny.module import ResolvedId, resolve_id

    resolved = resolve_id(id)
    return chat_ui(
        ResolvedId(f"{resolved}-chat"),
        messages=messages,
        enable_cancel=True,
        placeholder=placeholder,
        width=width,
        height=height,
        fill=fill,
        icon_assistant=icon_assistant,
        footer=footer,
        **kwargs,  # pyright: ignore[reportArgumentType]
    )


class ChatServerState:
    """
    Return value from :func:`~shinychat.chat_mod_server`.

    Provides reactive access to the chat module state and methods to interact with
    the chat programmatically.
    """

    def __init__(
        self,
        *,
        _chat: Chat,
        _last_input_rv: Any,
        _last_turn_rv: Any,
        _status_rv: Any,
        _client_ref: list[Any],
        _set_client_fn: Callable[..., None],
        _clear_fn: Callable[..., Any],
        _set_greeting_fn: Callable[..., Any],
    ):
        self._chat = _chat
        self._last_input_rv = _last_input_rv
        self._last_turn_rv = _last_turn_rv
        self._status_rv = _status_rv
        self._client_ref = _client_ref
        self._set_client_fn = _set_client_fn
        self._clear_fn = _clear_fn
        self._set_greeting_fn = _set_greeting_fn

    def last_input(self) -> Optional[str]:
        """
        Reactively read the last user input message.
        """
        return self._last_input_rv()

    def last_turn(self) -> Any:
        """
        Reactively read the last assistant turn.

        Returns a ``chatlas.Turn`` object or ``None`` if no turn has completed.
        """
        return self._last_turn_rv()

    def status(self) -> Literal["streaming", "idle"]:
        """
        Reactively read the streaming status.

        Returns ``"streaming"`` while a response is being generated, or ``"idle"``
        otherwise.
        """
        return self._status_rv()

    @property
    def client(self) -> chatlas.Chat[Any, Any]:
        """
        The current chatlas client.
        """
        return self._client_ref[0]

    def update_user_input(
        self,
        value: Optional[str] = None,
        *,
        placeholder: Optional[str] = None,
        submit: bool = False,
        focus: bool = False,
    ) -> None:
        """
        Update the chat user input.

        Parameters
        ----------
        value
            The value to set in the user input box.
        placeholder
            New placeholder text.
        submit
            Whether to automatically submit the value.
        focus
            Whether to move focus to the input element.
        """
        self._chat.update_user_input(
            value=value, placeholder=placeholder, submit=submit, focus=focus
        )

    async def append(
        self,
        response: Any,
        *,
        role: str = "assistant",
        icon: Optional[Union[HTML, Tag, TagList]] = None,
    ) -> None:
        """
        Append a message or stream to the chat.

        Parameters
        ----------
        response
            A message string, HTML, or async iterable of chunks.
        role
            The role of the message (``"assistant"`` or ``"user"``).
        icon
            Optional icon to display next to the message.
        """
        if isinstance(response, AsyncIterable):
            stream_icon = icon if isinstance(icon, (HTML, Tag)) else None
            await self._chat.append_message_stream(response, icon=stream_icon)
        else:
            msg: ChatMessageDict = {
                "content": str(response) if not isinstance(response, (HTML, Tag, TagList)) else response,  # type: ignore[typeddict-item]
                "role": role,  # type: ignore[typeddict-item]
            }
            await self._chat.append_message(msg, icon=icon)

    async def clear(
        self,
        messages: Optional[list[Any]] = None,
        greeting: bool = False,
        client_history: Literal["clear", "set", "append", "keep"] = "clear",
    ) -> None:
        """
        Clear the chat messages.

        Parameters
        ----------
        messages
            Optional list of messages to display after clearing. Each item should be a
            dict with ``role`` and ``content`` keys, or a string (treated as an assistant
            message).
        greeting
            If ``True``, also clear the greeting, which causes the
            ``{id}_greeting_requested`` input to fire again.
        client_history
            How to handle the chatlas client's turn history:

            - ``"clear"``: wipe all turns (default).
            - ``"set"``: replace turns with the ``messages`` provided.
            - ``"append"``: append ``messages`` to the existing turns.
            - ``"keep"``: leave the client turns unchanged.
        """
        await self._clear_fn(
            messages=messages, greeting=greeting, client_history=client_history
        )

    async def set_greeting(
        self,
        greeting: Union[str, HTML, Tag, TagList, ChatGreeting, None],
    ) -> None:
        """
        Set or clear the chat greeting.

        Parameters
        ----------
        greeting
            The greeting content. See :meth:`~shinychat.Chat.set_greeting` for details.
        """
        await self._set_greeting_fn(greeting)

    def set_client(self, new_client: chatlas.Chat[Any, Any], *, sync: bool = True) -> None:
        """
        Replace the chatlas client.

        If the chat is currently streaming, the swap is deferred until the stream
        completes.

        Parameters
        ----------
        new_client
            The new chatlas client to use.
        sync
            If ``True`` (the default), the new client's turn history, system prompt,
            and tools are set to match the current client before swapping.
        """
        self._set_client_fn(new_client, sync=sync)


def chat_mod_server(
    id: str,
    client: chatlas.Chat[Any, Any],
    *,
    greeting: Optional[
        Union[str, HTML, TagList, ChatGreeting, Callable[..., Any]]
    ] = None,
    bookmark_on_input: bool = True,
    bookmark_on_response: bool = True,
) -> ChatServerState:
    """
    Server for a batteries-included chat module.

    Automatically wires a chatlas client to the chat UI created by
    :func:`~shinychat.chat_mod_ui`, handling streaming, cancellation, bookmarking,
    and optional greetings.

    Parameters
    ----------
    id
        The module ID. Must match the ``id`` passed to :func:`~shinychat.chat_mod_ui`.
    client
        A chatlas client (e.g., ``chatlas.ChatOpenAI()``) used to generate responses.
    greeting
        An optional greeting shown before any conversation messages. Accepts:

        - A static string, :class:`~htmltools.HTML`, :class:`~htmltools.TagList`, or
          :func:`~shinychat.chat_greeting`.
        - A callable that returns a greeting. The callable may optionally accept a
          ``client`` argument; if so, a fresh clone of ``client`` (with empty turn
          history) is passed to it. The callable is re-invoked each time
          ``{id}_greeting_requested`` fires (on first view and after ``clear()``).
    bookmark_on_input
        Whether to trigger a bookmark when the user submits a message.
    bookmark_on_response
        Whether to trigger a bookmark when the assistant finishes responding.

    Returns
    -------
    :
        A :class:`~shinychat.ChatServerState` instance with reactive accessors and
        methods for interacting with the chat programmatically.
    """
    try:
        import chatlas as _chatlas  # noqa: F401
    except ImportError as e:
        raise ImportError(
            "chatlas is required for chat_mod_server(). "
            "Install it with: pip install chatlas"
        ) from e

    from shiny import module, reactive

    @module.server
    def _server(
        input: Any,
        output: Any,
        session: Any,
        client: Any,
        greeting: Any,
        bookmark_on_input: bool,
        bookmark_on_response: bool,
    ) -> ChatServerState:
        chat = Chat("chat")
        client_ref: list[Any] = [client]

        _last_input: reactive.Value[Optional[str]] = reactive.Value(None)
        _last_turn: reactive.Value[Any] = reactive.Value(None)
        _status: reactive.Value[Literal["streaming", "idle"]] = reactive.Value("idle")
        _pending_swap: reactive.Value[Optional[dict[str, Any]]] = reactive.Value(None)

        def _swap_client(new_client: Any, sync: bool) -> None:
            if sync:
                new_client.set_turns(client_ref[0].get_turns())
                new_client.system_prompt = client_ref[0].system_prompt
                new_client.set_tools(client_ref[0].get_tools())
            client_ref[0] = new_client

            with reactive.isolate():
                _re_enable_bookmarking()

        def _re_enable_bookmarking() -> None:
            try:
                chat.enable_bookmarking(
                    client_ref[0],
                    bookmark_on="response" if bookmark_on_response else None,
                )
            except Exception:
                pass

        def _set_client(new_client: Any, sync: bool = True) -> None:
            with reactive.isolate():
                streaming = _status() == "streaming"

            if streaming:
                _pending_swap.set({"client": new_client, "sync": sync})
                return

            _swap_client(new_client, sync)

        @chat.on_user_submit
        async def _handle_submit(user_input: str) -> None:
            _last_input.set(user_input)
            _status.set("streaming")
            response = client_ref[0].stream_async(user_input, content="all")
            await chat.append_message_stream(response)

        @reactive.effect
        @reactive.event(lambda: input["chat_cancel"])
        def _on_cancel() -> None:
            stream = chat.latest_message_stream
            stream.cancel()

        @reactive.effect
        def _on_stream_complete() -> None:
            stream = chat.latest_message_stream
            stream_status = stream.status()

            if stream_status == "success":
                with reactive.isolate():
                    _last_turn.set(client_ref[0].get_last_turn())
                _status.set("idle")
            elif stream_status in ("error", "cancelled"):
                _status.set("idle")

            with reactive.isolate():
                swap = _pending_swap()
                current_status = _status()

            if swap is not None and current_status != "streaming":
                _pending_swap.set(None)
                _swap_client(swap["client"], swap["sync"])

        async def _clear(
            messages: Optional[list[Any]] = None,
            greeting: bool = False,
            client_history: Literal["clear", "set", "append", "keep"] = "clear",
        ) -> None:
            await chat.clear_messages(greeting=greeting)

            normalized: list[dict[str, str]] = []
            if messages is not None:
                for msg in messages:
                    if isinstance(msg, str):
                        normalized.append({"role": "assistant", "content": msg})
                    elif isinstance(msg, dict):
                        normalized.append({
                            "role": msg.get("role", "assistant"),
                            "content": str(msg.get("content", "")),
                        })
                    else:
                        normalized.append({"role": "assistant", "content": str(msg)})

                for msg in normalized:
                    await chat.append_message({
                        "content": msg["content"],
                        "role": msg["role"],
                    })

            if client_history == "clear":
                client_ref[0].set_turns([])
            elif client_history == "set":
                client_ref[0].set_turns([])
            elif client_history == "append":
                pass
            # "keep" does nothing

            _last_turn.set(None)
            _last_input.set(None)

        if callable(greeting) and not isinstance(greeting, (str, ChatGreeting)):
            greeting_sig = inspect.signature(greeting)
            greeting_params = list(greeting_sig.parameters.keys())

            @reactive.effect
            @reactive.event(lambda: input["chat_greeting_requested"])
            async def _on_greeting_requested() -> None:
                args: dict[str, Any] = {}
                if "client" in greeting_params:
                    greeter = copy.deepcopy(client_ref[0])
                    greeter.set_turns([])
                    args["client"] = greeter

                result: Any = greeting(**args)
                if inspect.isawaitable(result):
                    result = await result
                await chat.set_greeting(result)

        elif greeting is not None:

            @reactive.effect
            async def _set_initial_greeting() -> None:
                await chat.set_greeting(greeting)
                _set_initial_greeting.destroy()  # type: ignore[attr-defined]

        try:
            chat.enable_bookmarking(
                client_ref[0],
                bookmark_on="response" if bookmark_on_response else None,
            )
        except Exception:
            pass

        return ChatServerState(
            _chat=chat,
            _last_input_rv=_last_input,
            _last_turn_rv=_last_turn,
            _status_rv=_status,
            _client_ref=client_ref,
            _set_client_fn=_set_client,
            _clear_fn=_clear,
            _set_greeting_fn=chat.set_greeting,
        )

    return _server(
        id,
        client=client,
        greeting=greeting,
        bookmark_on_input=bookmark_on_input,
        bookmark_on_response=bookmark_on_response,
    )
