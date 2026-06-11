from __future__ import annotations

import inspect
import json
import re
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import (
    TYPE_CHECKING,
    Any,
    AsyncIterable,
    Awaitable,
    Callable,
    Iterable,
    Literal,
    Optional,
    Sequence,
    Tuple,
    Union,
    cast,
    overload,
)
from weakref import WeakValueDictionary

from htmltools import (
    HTML,
    HTMLDependency,
    Tag,
    TagAttrValue,
    TagChild,
    TagList,
    css,
)
from pydantic import ValidationError

from . import _utils
from ._chat_bookmark import (
    BookmarkCancelCallback,
    CancelCallback,
    ClientWithState,
    get_chatlas_state,
    is_chatlas_chat_client,
    set_chatlas_state,
)
from ._chat_normalize import message_content, message_content_chunk
from ._chat_segments import (
    append_to_segments,
    copy_segments,
    has_mixed_content_types,
    segments_content,
    segments_deps,
    serialize_segments,
)
from ._chat_types import (
    ChatAction,
    ChatGreeting,
    ChatMessage,
    ChatMessageDict,
    ClearAction,
    ContentSegment,
    GreetingOptions,
    MessagePayload,
    SerializedDep,
    SlashCommandDef,
    StoredMessage,
    chat_greeting,
)
from ._html_deps_py_shiny import shinychat_dependency
from ._typing_extensions import TypeGuard
from ._utils_types import DEPRECATED, DEPRECATED_TYPE, MISSING, MISSING_TYPE

if TYPE_CHECKING:
    import chatlas
    from shiny.bookmark import BookmarkState, RestoreState
    from shiny.bookmark._types import BookmarkStore
    from shiny.reactive import ExtendedTask
    from shiny.reactive._reactives import Effect_
    from shiny.types import Jsonifiable
    from shiny.ui.css import CssUnit

    from ._chat_client import ChatClient


else:
    chatlas = object

__all__ = (
    "Chat",
    "ChatExpress",
    "ChatGreeting",
    "ChatMessage",
    "chat_greeting",
    "chat_ui",
    "ChatMessageDict",
)


# TODO: UserInput might need to be a list of dicts if we want to support multiple
# user input content types
TransformUserInput = Callable[[str], Union[str, None]]
TransformUserInputAsync = Callable[[str], Awaitable[Union[str, None]]]
TransformAssistantResponse = Callable[[str], Union[str, HTML, None]]
TransformAssistantResponseAsync = Callable[
    [str], Awaitable[Union[str, HTML, None]]
]
TransformAssistantResponseChunk = Callable[
    [str, str, bool], Union[str, HTML, None]
]
TransformAssistantResponseChunkAsync = Callable[
    [str, str, bool], Awaitable[Union[str, HTML, None]]
]
TransformAssistantResponseFunction = Union[
    TransformAssistantResponse,
    TransformAssistantResponseAsync,
    TransformAssistantResponseChunk,
    TransformAssistantResponseChunkAsync,
]
UserSubmitFunction0 = Union[
    Callable[[], None],
    Callable[[], Awaitable[None]],
]
UserSubmitFunction1 = Union[
    Callable[[str], None],
    Callable[[str], Awaitable[None]],
]
UserSubmitFunction = Union[
    UserSubmitFunction0,
    UserSubmitFunction1,
]


@dataclass(frozen=True)
class SlashCommandRegistration:
    handler: UserSubmitFunction | None
    takes_args: bool
    definition: SlashCommandDef


ChunkOption = Literal["start", "end", True, False]

PendingMessage = Tuple[
    Any,
    ChunkOption,
    Literal["append", "replace"],
    Union[str, None],
]


class Chat:
    """
    Create a chat interface.

    A UI component for building conversational interfaces. With it, end users can submit
    messages, which will cause a `.on_user_submit()` callback to run. That callback gets
    passed the user input message, which can be used to generate a response. The
    response can then be appended to the chat using `.append_message()` or
    `.append_message_stream()`.

    Here's a rough outline for how to implement a `Chat`:

    ```python
    from shiny.express import ui

    # Create and display chat instance
    chat = ui.Chat(id="my_chat")
    chat.ui()


    # Define a callback to run when the user submits a message
    @chat.on_user_submit
    async def handle_user_input(user_input: str):
        # Create a response message stream
        response = await my_model.generate_response(user_input, stream=True)
        # Append the response into the chat
        await chat.append_message_stream(response)
    ```

    In the outline above, `my_model.generate_response()` is a placeholder for
    the function that generates a response based on the chat's messages. This function
    will look different depending on the model you're using, but it will generally
    involve passing the messages to the model and getting a response back. Also, you'll
    typically have a choice to `stream=True` the response generation, and in that case,
    you'll use `.append_message_stream()` instead of `.append_message()` to append the
    response to the chat. Streaming is preferrable when available since it allows for
    more responsive and scalable chat interfaces.

    It is also highly recommended to use a package like
    [chatlas](https://posit-dev.github.io/chatlas/) to generate responses, especially
    when responses should be aware of the chat history, support tool calls, etc.
    See this [article](https://posit-dev.github.io/chatlas/web-apps.html) to learn more.

    Thinking display
    ----------------

    When a model produces reasoning or "thinking" tokens, shinychat renders them
    in a collapsible panel above the response. The panel streams the model's
    reasoning in real time, then auto-collapses when the response begins.

    Two paths are supported:

    1. **chatlas `ContentThinking` objects.** Models with a structured thinking
       API (e.g., Claude with extended thinking) emit `ContentThinking` objects
       during streaming. shinychat detects these and routes them to the thinking
       panel automatically.

    2. **Raw `<thinking>` tags.** Many open-source and local models (DeepSeek,
       QwQ, Qwen, etc.) emit `<thinking>...</thinking>` tags in their markdown
       output. shinychat detects these tags during streaming and renders the
       enclosed text in the thinking panel with no extra configuration.

    **Topic labels:** You can get labeled sub-sections within the thinking panel
    by asking the model to emit `<topic>...</topic>` tags in its reasoning.
    These show up as section headings inside the panel, and the current topic
    appears in the collapsed header as a live status indicator.

    To use topic labels, add something like this to your system prompt::

        When thinking through a problem, wrap brief topic labels in <topic> tags
        to indicate what you're currently reasoning about. For example:
        <topic>parsing the input</topic>

    Topic labels are optional. Without them, the thinking panel still works --
    it just won't have sub-section headings.

    Parameters
    ----------
    id
        A unique identifier for the chat session. In Shiny Core, make sure this id
        matches a corresponding :func:`~shiny.ui.chat_ui` call in the UI.
    client
        A chatlas client (e.g., ``chatlas.ChatOpenAI()``). When provided,
        streaming, cancellation, and bookmarking are wired up automatically.
        This includes registering an :meth:`~shinychat.Chat.on_user_submit`
        callback that streams the client's response to each user message, so you
        don't need to write one yourself. Any additional ``@chat.on_user_submit``
        handlers you register still run, in addition to (not in place of) this
        one.
        The resulting :attr:`chat.client` exposes a
        :class:`~shinychat.types.ChatClient` wrapper for swapping models
        mid-session (``.set()``) and resetting the conversation (``.clear()``).
    greeting
        Content to display as a welcome message before any conversation. Can be
        a string, :class:`~htmltools.HTML`, :class:`~htmltools.Tag`,
        :class:`~htmltools.TagList`, :class:`~shinychat.chat_greeting`, or a
        callable that returns one of those types. A callable greeting is invoked
        when the chat is visible and empty; if the callable accepts a ``client``
        parameter (and ``client=`` was provided), a deep-copy of the chatlas
        client with empty turns is passed so the greeting can be LLM-generated
        without polluting conversation history.
    messages
        Deprecated. Use `chat.ui(messages=...)` instead.
    on_error
        How to handle errors that occur in response to user input. When `"unhandled"`,
        the app will stop running when an error occurs. Otherwise, a notification
        is displayed to the user and the app continues to run.

        * `"auto"`: Sanitize the error message if the app is set to sanitize errors,
          otherwise display the actual error message.
        * `"actual"`: Display the actual error message to the user.
        * `"sanitize"`: Sanitize the error message before displaying it to the user.
        * `"unhandled"`: Do not display any error message to the user.
    tokenizer
        Removed. Raises ``TypeError`` if provided. Use your LLM provider
        (e.g., chatlas, LangChain) to manage token limits instead.
    """

    def __init__(
        self,
        id: str,
        *,
        client: "chatlas.Chat[Any, Any] | None" = None,
        greeting: "str | HTML | Tag | TagList | ChatGreeting | Callable[..., Any] | None" = None,
        messages: Sequence[Any] = (),
        on_error: Literal["auto", "actual", "sanitize", "unhandled"] = "auto",
        tokenizer: DEPRECATED_TYPE = DEPRECATED,
    ):
        from shiny._deprecated import warn_deprecated
        from shiny.module import ResolvedId, resolve_id
        from shiny.session import require_active_session

        if not isinstance(id, str):
            raise TypeError("`id` must be a string.")

        if messages:
            warn_deprecated(
                "`Chat(messages=...)` is deprecated. Use `.ui(messages=...)` instead."
            )

        if not isinstance(tokenizer, DEPRECATED_TYPE):
            raise TypeError(
                "`Chat(tokenizer=...)` has been removed. "
                "Token counting and message trimming are no longer supported by shinychat. "
                "Use your LLM provider (e.g., chatlas, LangChain) to manage conversation context instead."
            )

        self.id = resolve_id(id)
        self.user_input_id = ResolvedId(f"{self.id}_user_input")
        self._slash_command_id = ResolvedId(f"{self.id}_slash_command")
        self._transform_user: TransformUserInputAsync | None = None
        self._transform_assistant: (
            TransformAssistantResponseChunkAsync | None
        ) = None

        # TODO: remove the `None` when this PR lands:
        # https://github.com/posit-dev/py-shiny/pull/793/files
        self._session = require_active_session(None)

        # Default to sanitizing until we know the app isn't sanitizing errors
        if on_error == "auto":
            on_error = "sanitize"
            app = self._session.app
            if app is not None and not app.sanitize_errors:  # type: ignore
                on_error = "actual"

        self.on_error = on_error

        # Chunked messages get accumulated (using this property) before changing state
        self._current_stream_segments: list[ContentSegment] = []
        self._current_stream_id: str | None = None
        self._pending_messages: list[PendingMessage] = []

        # For tracking message stream state when entering/exiting nested streams
        self._message_stream_segments_checkpoint: list[ContentSegment] = []

        # Keep track of effects so we can destroy them when the chat is destroyed
        self._effects: list["Effect_"] = []
        self._cancel_bookmarking_callbacks: CancelCallback | None = None

        # Initialize chat state and user input effect
        from shiny import reactive
        from shiny.session import session_context

        with session_context(self._session):
            # Initialize message state
            self._messages: reactive.Value[tuple[StoredMessage, ...]] = (
                reactive.Value(())
            )

            # `None` until the first registration, which lets us skip the
            # redundant initial sync (the client already initializes to `[]`).
            # An empty dict, by contrast, is sent so that removing the last
            # command clears the client's palette.
            self._slash_commands: reactive.Value[
                dict[str, SlashCommandRegistration] | None
            ] = reactive.Value(None)

            self._latest_user_input: reactive.Value[
                StoredMessage | None
            ] = reactive.Value(None)

            @reactive.extended_task
            async def _mock_task() -> str:
                return ""

            self._latest_stream: reactive.Value[
                reactive.ExtendedTask[[], str]
            ] = reactive.Value(_mock_task)

            # TODO: deprecate messages once we start promoting managing LLM message
            # state through other means
            async def _append_init_messages():
                for msg in messages:
                    await self.append_message(msg)

            @reactive.effect
            async def _init_chat():
                await _append_init_messages()

            self._append_init_messages = _append_init_messages
            self._init_chat = _init_chat

            # When user input is submitted, store it in the chat state
            # (runs before other effects so `.messages()` includes the latest input)
            @reactive.effect(priority=9999)
            @reactive.event(self._user_input)
            async def _on_user_input():
                msg = ChatMessage(content=self._user_input(), role="user")
                self._store_message(msg)

            @reactive.effect
            async def _sync_slash_commands():
                cmds = self._slash_commands()
                if cmds is None:
                    return
                await self._send_action(
                    {
                        "type": "update_slash_commands",
                        "commands": [reg.definition for reg in cmds.values()],
                    }
                )

            @reactive.effect
            @reactive.event(self._slash_command_input)
            async def _on_slash_command():
                data = self._slash_command_input()
                command = data.get("command", "")
                user_text = data.get("userText", "")
                echo = bool(data.get("echo", True))
                if echo:
                    full_text = f"/{command} {user_text}".rstrip()
                    msg = ChatMessage(content=full_text, role="user")
                    self._store_message(msg)
                cmds = self._slash_commands()
                reg = cmds.get(command) if cmds else None
                try:
                    if reg is not None and reg.handler is not None:
                        if reg.takes_args:
                            await _utils.wrap_async(
                                cast(UserSubmitFunction1, reg.handler)
                            )(user_text)
                        else:
                            await _utils.wrap_async(
                                cast(UserSubmitFunction0, reg.handler)
                            )()
                except Exception as e:
                    await self._raise_exception(e)
                finally:
                    await self._remove_loading_message()

            self._effects.append(_init_chat)
            self._effects.append(_on_user_input)
            self._effects.append(_sync_slash_commands)
            self._effects.append(_on_slash_command)

        # Prevent repeated calls to Chat() with the same id from accumulating effects
        instance_id = self.id + "_session" + self._session.id
        instance = CHAT_INSTANCES.pop(instance_id, None)
        if instance is not None:
            instance.destroy()
        CHAT_INSTANCES[instance_id] = self

        self.client: "ChatClient | None" = None
        if client is not None:
            self._setup_client(client)

        if greeting is not None:
            from ._chat_client import setup_greeting

            setup_greeting(self, greeting, self._session)

    def _setup_client(
        self,
        client: "chatlas.Chat[Any, Any]",
    ) -> None:
        from chatlas import StreamController
        from shiny import reactive
        from shiny.session import session_context

        from ._chat_client import ChatClient

        chat_client = ChatClient(
            chat=self,
            client=client,
        )
        self.client = chat_client

        controller = StreamController()
        cancel_input_id = f"{self.id}_cancel"

        # Match the rest of `__init__`: create these effects under the chat's
        # own session so they attach correctly even when `Chat(...)` is
        # constructed outside that session's reactive context.
        with session_context(self._session):

            @self.on_user_submit
            async def _on_user_submit(user_input: str) -> None:
                response = await chat_client.value.stream_async(
                    user_input,
                    content="all",
                    controller=controller,
                )
                await self.append_message_stream(response)

            # A `client=` wires up cancellation, so enable the stop button
            # without requiring `enable_cancel=True` in `chat_ui()`. It only
            # surfaces while streaming, so sending this once at session start
            # (the effect has no reactive dependencies) is enough.
            @reactive.effect
            async def _enable_cancel_ui() -> None:
                await self._send_action(
                    {"type": "update_cancel", "enable_cancel": True}
                )

            @reactive.effect
            @reactive.event(self._session.input[cancel_input_id])
            async def _on_cancel() -> None:
                controller.cancel()

            @reactive.effect
            async def _on_stream_complete() -> None:
                status = self.latest_message_stream.status()
                if status == "running":
                    return

                swap = chat_client._pending_swap
                if swap is None:
                    return
                chat_client._pending_swap = None
                new_client, sync = swap
                chat_client._swap_client(new_client, sync=sync)

            self._effects.append(_enable_cancel_ui)
            self._effects.append(_on_cancel)
            self._effects.append(_on_stream_complete)

            cancel_bm = self.enable_bookmarking(client, bookmark_on="response")
            chat_client._cancel_bookmarking = cancel_bm

    @overload
    def on_user_submit(self, fn: UserSubmitFunction) -> Effect_: ...

    @overload
    def on_user_submit(
        self,
    ) -> Callable[[UserSubmitFunction], Effect_]: ...

    def on_user_submit(
        self, fn: UserSubmitFunction | None = None
    ) -> Effect_ | Callable[[UserSubmitFunction], Effect_]:
        """
        Define a function to invoke when user input is submitted.

        Apply this method as a decorator to a function (`fn`) that should be invoked
        when the user submits a message. This function can take an optional argument,
        which will be the user input message.

        In many cases, the implementation of `fn` should also do the following:

        1. Generate a response based on the user input.
          * If the response should be aware of chat history, use a package
             like [chatlas](https://posit-dev.github.io/chatlas/) to manage the chat
             state, or use the `.messages()` method to get the chat history.
        2. Append that response to the chat component using `.append_message()` ( or
           `.append_message_stream()` if the response is streamed).

        Parameters
        ----------
        fn
            A function to invoke when user input is submitted.

        Note
        ----
        This method creates a reactive effect that only gets invalidated when the user
        submits a message. Thus, the function `fn` can read other reactive dependencies,
        but it will only be re-invoked when the user submits a message.
        """

        def create_effect(fn: UserSubmitFunction):
            from shiny import reactive

            fn_params = inspect.signature(fn).parameters

            @reactive.effect
            @reactive.event(self._user_input)
            async def handle_user_input():
                try:
                    if len(fn_params) > 1:
                        raise ValueError(
                            "A on_user_submit function should not take more than 1 argument"
                        )
                    elif len(fn_params) == 1:
                        input = self.user_input() or ""
                        afunc = _utils.wrap_async(cast(UserSubmitFunction1, fn))
                        await afunc(input)
                    else:
                        afunc = _utils.wrap_async(cast(UserSubmitFunction0, fn))
                        await afunc()
                except Exception as e:
                    await self._raise_exception(e)

            self._effects.append(handle_user_input)

            return handle_user_input

        if fn is None:
            return create_effect
        else:
            return create_effect(fn)

    @overload
    def slash_command(
        self,
        name: str,
        description: str,
        *,
        echo: bool | None = None,
        force: bool = False,
    ) -> Callable[[UserSubmitFunction], UserSubmitFunction]: ...

    @overload
    def slash_command(
        self,
        name: str,
        description: str,
        fn: UserSubmitFunction | None,
        *,
        echo: bool | None = None,
        force: bool = False,
    ) -> Callable[[], None]: ...

    def slash_command(
        self,
        name: str,
        description: str,
        fn: UserSubmitFunction | None | MISSING_TYPE = MISSING,
        *,
        echo: bool | None = None,
        force: bool = False,
    ) -> Callable[[UserSubmitFunction], UserSubmitFunction] | Callable[[], None]:
        """
        Register a slash command and its handler.

        Can be used as a decorator (handler supplied by decoration) or called
        directly with ``fn=``. Pass ``fn=None`` to register a *client-side*
        command — one with no server handler, handled in JavaScript via the
        ``shiny:chat-slash-command`` DOM event (see the docs).

        Parameters
        ----------
        name
            The slash command name (without the leading ``/``). Must contain only
            alphanumeric characters, underscores, or hyphens.
        description
            A short description shown in the command palette.
        fn
            The handler function (0 or 1 argument; one argument receives the text
            after the command name). Omit it to use ``slash_command`` as a
            decorator. Pass ``None`` explicitly to register a client-side command
            with no server handler.
        echo
            Whether invoking the command participates in the conversation: adds
            the ``/cmd user_input`` user message, shows a loading state, and stores the
            invocation in history. Defaults to ``True`` when a handler is provided
            and ``False`` otherwise. Set ``echo=False`` for a server handler that
            runs purely for its side effects (e.g. opening a modal).
        force
            Whether to overwrite an existing command with the same name.

        Returns
        -------
        :
            A decorator when ``fn`` is omitted; otherwise a callable that removes
            the command.
        """

        from shiny import reactive

        def _register(handler: UserSubmitFunction | None) -> None:
            if not re.fullmatch(r"[a-zA-Z0-9_-]+", name):
                raise ValueError(
                    f"Slash command name must contain only alphanumeric characters, underscores, or hyphens, got {name!r}"
                )
            with reactive.isolate():
                cmds = dict(self._slash_commands() or {})
            if not force and name in cmds:
                raise ValueError(
                    f"Slash command {name!r} is already registered. "
                    f"Use `force=True` to overwrite it."
                )
            resolved_echo = (handler is not None) if echo is None else echo
            cmd_def = SlashCommandDef(
                name=name, description=description, echo=resolved_echo
            )
            takes_args = False
            if handler is not None:
                n_params = len(inspect.signature(handler).parameters)
                if n_params > 1:
                    raise ValueError(
                        f"Slash command handler for {name!r} must accept 0 or 1 "
                        f"argument, got {n_params}"
                    )
                takes_args = n_params >= 1
            cmds[name] = SlashCommandRegistration(
                handler=handler,
                takes_args=takes_args,
                definition=cmd_def,
            )
            self._slash_commands.set(cmds)

        if isinstance(fn, MISSING_TYPE):

            def decorator(handler: UserSubmitFunction) -> UserSubmitFunction:
                _register(handler)
                return handler

            return decorator
        else:
            _register(fn)
            return self._remove_slash_command_fn(name)

    def remove_slash_command(self, name: str) -> None:
        """
        Remove a previously registered slash command by name.

        Parameters
        ----------
        name
            The name of the command to remove (without the leading ``/``).
        """
        from shiny import reactive

        with reactive.isolate():
            cmds = dict(self._slash_commands() or {})
        cmds.pop(name, None)
        self._slash_commands.set(cmds)

    def _remove_slash_command_fn(self, name: str) -> Callable[[], None]:
        def remove() -> None:
            self.remove_slash_command(name)

        return remove

    async def _raise_exception(
        self,
        e: BaseException,
    ) -> None:
        from shiny.types import NotifyException

        if self.on_error == "unhandled":
            raise e
        else:
            await self._remove_loading_message()
            sanitize = self.on_error == "sanitize"
            msg = f"Error in Chat('{self.id}'): {str(e)}"
            raise NotifyException(msg, sanitize=sanitize) from e

    def messages(
        self,
        *,
        format: DEPRECATED_TYPE = DEPRECATED,
        token_limits: DEPRECATED_TYPE = DEPRECATED,
    ) -> tuple[ChatMessageDict, ...]:
        """
        Reactively read chat messages

        Obtain chat messages within a reactive context.

        Parameters
        ----------
        format
            Removed. Raises ``TypeError`` if provided. Use your LLM provider
            (e.g., chatlas, LangChain) to manage message formatting instead.
        token_limits
            Removed. Raises ``TypeError`` if provided. Use your LLM provider
            (e.g., chatlas, LangChain) to manage token limits instead.

        Note
        ----
        Messages are listed in the order they were added. As a result, when this method
        is called in a `.on_user_submit()` callback (as it most often is), the last
        message will be the most recent one submitted by the user.

        Returns
        -------
        tuple[ChatMessageDict, ...]
            A tuple of chat messages.
        """
        if not isinstance(format, DEPRECATED_TYPE):
            raise TypeError(
                "`.messages(format=...)` has been removed. "
                "Provider-specific message formatting is no longer supported by shinychat. "
                "Use your LLM provider (e.g., chatlas, LangChain) to manage conversation state instead."
            )

        if not isinstance(token_limits, DEPRECATED_TYPE):
            raise TypeError(
                "`.messages(token_limits=...)` has been removed. "
                "Token counting and message trimming are no longer supported by shinychat. "
                "Use your LLM provider (e.g., chatlas, LangChain) to manage conversation context instead."
            )

        messages = self._messages()

        res: list[ChatMessageDict] = []
        for m in messages:
            chat_msg = ChatMessageDict(content=str(m.content), role=m.role)
            if m.html_deps:
                chat_msg["html_deps"] = m.html_deps
            res.append(chat_msg)

        return tuple(res)

    async def append_message(
        self,
        message: Any,
        *,
        icon: HTML | Tag | TagList | None = None,
    ):
        """
        Append a message to the chat.

        Parameters
        ----------
        message
            A given message can be one of the following:

            * A string, which is interpreted as markdown and rendered to HTML on the
              client.
                * To prevent interpreting as markdown, mark the string as
                  :class:`~shiny.ui.HTML`.
            * A UI element (specifically, a :class:`~shiny.ui.TagChild`).
                * This includes :class:`~shiny.ui.TagList`, which take UI elements
                  (including strings) as children. In this case, strings are still
                  interpreted as markdown as long as they're not inside HTML.
            * A dictionary with `content` and `role` keys. The `content` key can contain
              content as described above, and the `role` key can be "assistant" or
              "user".
            * More generally, any type registered with :func:`shinychat.message_content`.

            **NOTE:** content may include specially formatted **input suggestion** links
            (see note below).
        icon
            An optional icon to display next to the message, currently only used for
            assistant messages. The icon can be any HTML element (e.g., an
            :func:`~shiny.ui.img` tag) or a string of HTML.

        Note
        ----
        :::{.callout-note title="Input suggestions"}
        Input suggestions are special links that send text to the user input box when
        clicked (or accessed via keyboard). They can be created in the following ways:

        * `<span class='suggestion'>Suggestion text</span>`: An inline text link that
            places 'Suggestion text' in the user input box when clicked.
        * `<img data-suggestion='Suggestion text' src='image.jpg'>`: An image link with
            the same functionality as above.
        * `<span data-suggestion='Suggestion text'>Actual text</span>`: An inline text
            link that places 'Suggestion text' in the user input box when clicked.

        A suggestion can also be submitted automatically by doing one of the following:

        * Adding a `submit` CSS class or a `data-suggestion-submit="true"` attribute to
          the suggestion element.
        * Holding the `Ctrl/Cmd` key while clicking the suggestion link.

        Note that a user may also opt-out of submitting a suggestion by holding the
        `Alt/Option` key while clicking the suggestion link.

        A markdown list (`<ul>` or `<ol>`) in which every item contains a single
        suggestion element is automatically rendered as a grid of clickable cards instead
        of inline chips. Each suggestion accepts an optional `title` attribute (plain
        text), which becomes the card heading; the suggestion's body becomes the card
        description. For ordered lists (`<ol>`), the list-item number is included in the
        heading.
        :::

        :::{.callout-note title="Streamed messages"}
        Use `.append_message_stream()` instead of this method when `stream=True` (or
        similar) is specified in model's completion method.
        :::
        """
        # If we're in a stream, queue the message
        if self._current_stream_id:
            self._pending_messages.append((message, False, "append", None))
            return

        msg = message_content(message)
        msg = await self._transform_message(msg)
        if msg is None:
            return
        self._store_message(msg)
        await self._send_append_message(
            message=msg,
            chunk=False,
            icon=icon,
        )

    @asynccontextmanager
    async def message_stream_context(self):
        """
        Message stream context manager.

        A context manager for appending streaming messages into the chat. This context
        manager can:

        1. Be used in isolation to append a new streaming message to the chat.
            * Compared to `.append_message_stream()` this method is more flexible but
              isn't non-blocking by default (i.e., it doesn't launch an extended task).
        2. Be nested within itself
            * Nesting is primarily useful for making checkpoints to `.replace()` back
              to (see the example below).
        3. Be used from within a `.append_message_stream()`
            * Useful for inserting additional content from another context into the
              stream (e.g., see the note about tool calls below).

        Yields
        ------
        :
            A `MessageStream` class instance, which has a method for `.append()`ing
            message content chunks to as well as a `.replace()` method to reset the
            stream back to its initial state (via `.replace("")`). Note that
            `.append()` supports the same message content types as `.append_message()`.

        Example
        -------
        ```python
        import asyncio

        from shiny import reactive
        from shiny.express import ui

        chat = ui.Chat(id="my_chat")
        chat.ui()


        @reactive.effect
        async def _():
            async with chat.message_stream_context() as msg:
                await msg.append("Starting stream...\n\nProgress:")
                async with chat.message_stream_context() as progress:
                    for x in [0, 50, 100]:
                        await progress.append(f" {x}%")
                        await asyncio.sleep(1)
                        await progress.replace("")
                await msg.replace("")
                await msg.append("Completed stream")
        ```

        Note
        ----
        A useful pattern for displaying tool calls in a chatbot is for the tool to
        display using `.message_stream_context()` while the the response generation is
        happening through `.append_message_stream()`. This allows the tool to display
        things like progress updates (or other "ephemeral" content) and optionally
        `.replace("")` the stream back to it's initial state when ready to display the
        "final" content.

        Note
        ----
        `.replace()` resets the stream to the checkpoint captured when this context was
        entered. It raises `ValueError` if the stream's content since that checkpoint
        spans multiple content types (e.g. thinking followed by markdown), because the
        replace wire action carries a single content type. Open a fresh
        `.message_stream_context()` before the mixed content if you need a clean
        checkpoint to replace back to.
        """
        # Checkpoint the current stream state so operation="replace" can return to it
        old_checkpoint = self._message_stream_segments_checkpoint
        self._message_stream_segments_checkpoint = copy_segments(self._current_stream_segments)

        # No stream currently exists, start one
        stream_id = self._current_stream_id
        is_root_stream = stream_id is None
        if is_root_stream:
            stream_id = _utils.private_random_id()
            await self._append_message_chunk(
                "", chunk="start", stream_id=stream_id
            )

        try:
            yield MessageStream(self, stream_id)
        finally:
            # Restore the checkpoint
            self._message_stream_segments_checkpoint = old_checkpoint

            # If this was the root stream, end it
            if is_root_stream:
                await self._append_message_chunk(
                    "",
                    chunk="end",
                    stream_id=stream_id,
                )

    async def _append_message_chunk(
        self,
        message: Any,
        *,
        chunk: Literal[True, "start", "end"] = True,
        stream_id: str,
        operation: Literal["append", "replace"] = "append",
        icon: HTML | Tag | TagList | None = None,
    ) -> None:
        # If currently we're in a *different* stream, queue the message chunk
        if self._current_stream_id and self._current_stream_id != stream_id:
            self._pending_messages.append(
                (message, chunk, operation, stream_id)
            )
            return

        self._current_stream_id = stream_id

        # Normalize various message types into a ChatMessage()
        msg = message_content_chunk(message)
        chunk_deps = msg.html_deps or []

        if is_tool_result(message) and message.request is not None:
            await self._hide_tool_request(message.request.id)  # type: ignore

        if operation == "replace":
            if has_mixed_content_types(
                self._message_stream_segments_checkpoint
            ):
                raise ValueError(
                    "Cannot `.replace()` a stream whose checkpoint spans multiple "
                    "content types (e.g. thinking followed by markdown). The replace "
                    "wire action carries a single content type, so a mixed checkpoint "
                    "cannot be restored. Open a `.message_stream_context()` before the "
                    "mixed content to get a clean checkpoint, or use `.append()`."
                )
            self._current_stream_segments = copy_segments(
                self._message_stream_segments_checkpoint
            )

        append_to_segments(
            self._current_stream_segments,
            msg.content,
            msg.content_type,
            chunk_deps or None,
        )

        stream_content = segments_content(self._current_stream_segments)

        if operation == "replace":
            msg.content = stream_content

        try:
            if self._needs_transform(msg):
                # Transforming may change the meaning of msg.content to be a *replace*
                # not *append*. So, update msg.content and the operation accordingly.
                chunk_content = msg.content
                msg.content = stream_content
                operation = "replace"
                msg = await self._transform_message(
                    msg, chunk=chunk, chunk_content=chunk_content
                )
                # Act like nothing happened if transformed to None
                if msg is None:
                    return
                if chunk == "end":
                    stream_deps = segments_deps(self._current_stream_segments)
                    serialized_deps = self._serialize_html_deps(stream_deps)
                    # _transform_message returns a single-segment StoredMessage, so all stream
                    # deps belong on segments[0].
                    if serialized_deps and msg.segments:
                        msg.segments[0].html_deps = serialized_deps
                    self._store_message(msg)
            elif chunk == "end":
                # When `operation="append"`, msg.content is just a chunk, but we must
                # store the full message
                segs = serialize_segments(self._current_stream_segments, self._serialize_html_deps)
                self._store_message(
                    StoredMessage(
                        role=msg.role,
                        segments=segs,
                    ),
                )

            # Send the message to the client
            await self._send_append_message(
                message=msg,
                chunk=chunk,
                operation=operation,
                icon=icon,
            )
        finally:
            if chunk == "end":
                self._current_stream_id = None
                self._current_stream_segments = []
                self._message_stream_segments_checkpoint = []

    async def append_message_stream(
        self,
        message: Iterable[Any] | AsyncIterable[Any],
        *,
        icon: HTML | Tag | None = None,
    ):
        """
        Append a message as a stream of message chunks.

        Parameters
        ----------
        message
            An (async) iterable of message chunks. Each chunk can be one of the
            following:

            * A string, which is interpreted as markdown and rendered to HTML on the
              client.
                * To prevent interpreting as markdown, mark the string as
                  :class:`~shiny.ui.HTML`.
            * A UI element (specifically, a :class:`~shiny.ui.TagChild`).
                * This includes :class:`~shiny.ui.TagList`, which take UI elements
                  (including strings) as children. In this case, strings are still
                  interpreted as markdown as long as they're not inside HTML.
            * A dictionary with `content` and `role` keys. The `content` key can contain
              content as described above, and the `role` key can be "assistant" or
              "user".
            * More generally, any type registered with :func:`shinychat.message_content_chunk`.

            **NOTE:** content may include specially formatted **input suggestion** links
            (see note below).
        icon
            An optional icon to display next to the message, currently only used for
            assistant messages. The icon can be any HTML element (e.g., an
            :func:`~shiny.ui.img` tag) or a string of HTML.

        Note
        ----
        ```{.callout-note title="Input suggestions"}
        Input suggestions are special links that send text to the user input box when
        clicked (or accessed via keyboard). They can be created in the following ways:

        * `<span class='suggestion'>Suggestion text</span>`: An inline text link that
            places 'Suggestion text' in the user input box when clicked.
        * `<img data-suggestion='Suggestion text' src='image.jpg'>`: An image link with
            the same functionality as above.
        * `<span data-suggestion='Suggestion text'>Actual text</span>`: An inline text
            link that places 'Suggestion text' in the user input box when clicked.

        A suggestion can also be submitted automatically by doing one of the following:

        * Adding a `submit` CSS class or a `data-suggestion-submit="true"` attribute to
          the suggestion element.
        * Holding the `Ctrl/Cmd` key while clicking the suggestion link.

        Note that a user may also opt-out of submitting a suggestion by holding the
        `Alt/Option` key while clicking the suggestion link.

        A markdown list (`<ul>` or `<ol>`) in which every item contains a single
        suggestion element is automatically rendered as a grid of clickable cards instead
        of inline chips. Each suggestion accepts an optional `title` attribute (plain
        text), which becomes the card heading; the suggestion's body becomes the card
        description. For ordered lists (`<ol>`), the list-item number is included in the
        heading.
        ```

        ```{.callout-note title="Streamed messages"}
        Use this method (over `.append_message()`) when `stream=True` (or similar) is
        specified in model's completion method.
        ```

        Returns
        -------
        :
            An extended task that represents the streaming task. The `.result()` method
            of the task can be called in a reactive context to get the final state of the
            stream.
        """
        from shiny import reactive

        message = _utils.wrap_async_iterable(message)

        # Run the stream in the background to get non-blocking behavior
        @reactive.extended_task
        async def _stream_task():
            return await self._append_message_stream(message, icon=icon)

        _stream_task()

        self._latest_stream.set(_stream_task)

        # Since the task runs in the background (outside/beyond the current context,
        # if any), we need to manually raise any exceptions that occur
        @reactive.effect
        async def _handle_error():
            e = _stream_task.error()
            if e:
                await self._raise_exception(e)
            _handle_error.destroy()  # type: ignore

        return _stream_task

    @property
    def latest_message_stream(self) -> ExtendedTask[[], str]:
        """
        React to changes in the latest message stream.

        Reactively reads for the :class:`~shiny.reactive.ExtendedTask` behind an
        `.append_message_stream()`.

        From the return value (i.e., the extended task), you can then:

        1. Reactively read for the final `.result()`.
        2. `.cancel()` the stream.
        3. Check the `.status()` of the stream.

        Returns
        -------
        :
            An extended task that represents the streaming task. The `.result()` method
            of the task can be called in a reactive context to get the final state of the
            stream.

        Note
        ----
        If no stream has yet been started when this method is called, then it returns an
        extended task with `.status()` of `"initial"` and that it status doesn't change
        state until a message is streamed.
        """
        return self._latest_stream()

    async def _append_message_stream(
        self,
        message: AsyncIterable[Any],
        icon: HTML | Tag | None = None,
    ):
        id = _utils.private_random_id()

        empty = ChatMessageDict(content="", role="assistant")
        await self._append_message_chunk(
            empty, chunk="start", stream_id=id, icon=icon
        )

        try:
            async for msg in message:
                await self._append_message_chunk(msg, chunk=True, stream_id=id)
            # The string returned to the caller mirrors StoredMessage.content
            # (thinking wrapped in <thinking> tags), not segments_content's bare join.
            return "".join(str(s) for s in self._current_stream_segments)
        finally:
            await self._append_message_chunk(empty, chunk="end", stream_id=id)
            await self._flush_pending_messages()

    async def _flush_pending_messages(self):
        pending = self._pending_messages
        self._pending_messages = []
        for msg, chunk, operation, stream_id in pending:
            if chunk is False:
                await self.append_message(msg)
            else:
                await self._append_message_chunk(
                    msg,
                    chunk=chunk,
                    operation=operation,
                    stream_id=cast(str, stream_id),
                )

    # Send a message to the UI
    async def _send_append_message(
        self,
        message: StoredMessage | ChatMessage,
        chunk: ChunkOption = False,
        operation: Literal["append", "replace"] = "append",
        icon: HTML | Tag | TagList | None = None,
    ):
        message = self._as_stored_message(message)

        if message.role == "system":
            return

        # Bare segment content (no <thinking> wrapping): on the wire, thinking
        # travels as raw text paired with content_type="thinking", and the
        # client builds the thinking block from that type. StoredMessage.content
        # is the flat-string form that re-wraps thinking in tags instead.
        content = "".join(s.content for s in message.segments)
        content_type = (
            message.segments[-1].content_type if message.segments else "markdown"
        )

        msg_payload: MessagePayload = {
            "role": message.role,
            "segments": message.wire_segments(),
        }
        if icon is not None:
            msg_payload["icon"] = str(icon)

        if chunk == "start":
            action: ChatAction = {"type": "chunk_start", "message": msg_payload}
            await self._send_action(action, message.html_deps)
        elif chunk == "end":
            if content:
                chunk_action: ChatAction = {
                    "type": "chunk",
                    "content": content,
                    "operation": operation,
                    "content_type": content_type,
                }
                await self._send_action(chunk_action, message.html_deps)
            await self._send_action({"type": "chunk_end"})
        elif chunk is True:
            chunk_action = {
                "type": "chunk",
                "content": content,
                "operation": operation,
                "content_type": content_type,
            }
            await self._send_action(chunk_action, message.html_deps)
        else:
            action = {"type": "message", "message": msg_payload}
            await self._send_action(action, message.html_deps)

    def _messages_for_bookmark(self) -> list[dict[str, Any]]:
        from shiny import reactive

        with reactive.isolate():
            messages = self._messages()

        return [m.model_dump(exclude_none=True) for m in messages]

    async def _restore_bookmark_message(self, message_dict: Any) -> None:
        try:
            stored = StoredMessage.model_validate(message_dict)
        except ValidationError as e:
            raise ValueError(
                "Cannot restore bookmark message: invalid or missing fields "
                "(bookmark likely written by an incompatible shinychat version)."
            ) from e
        self._store_message(stored)
        await self._send_append_message(stored)

    def transform_user_input(self, *args: object, **kwargs: object) -> object:
        raise TypeError(
            "`.transform_user_input()` has been removed. "
            "Instead, transform user input manually before passing it to your "
            "LLM provider (e.g., chatlas, LangChain)."
        )

    @overload
    def transform_assistant_response(
        self, fn: TransformAssistantResponseFunction
    ) -> None: ...

    @overload
    def transform_assistant_response(
        self,
    ) -> Callable[[TransformAssistantResponseFunction], None]: ...

    def transform_assistant_response(
        self,
        fn: TransformAssistantResponseFunction | None = None,
    ) -> None | Callable[[TransformAssistantResponseFunction], None]:
        """
        Deprecated. Assistant response transformation features will be removed in a future version.
        """
        from shiny._deprecated import warn_deprecated

        warn_deprecated(
            "The `.transform_assistant_response` decorator is deprecated. "
            "Assistant response transformation features will be removed in a future version. "
            "See here for more details: https://github.com/posit-dev/shinychat/pull/91"
        )

        def _set_transform(
            fn: TransformAssistantResponseFunction,
        ):
            nparams = len(inspect.signature(fn).parameters)
            if nparams == 1:
                fn = cast(
                    Union[
                        TransformAssistantResponse,
                        TransformAssistantResponseAsync,
                    ],
                    fn,
                )
                fn = _utils.wrap_async(fn)

                async def _transform_wrapper(
                    content: str, chunk: str, done: bool
                ):
                    return await fn(content)

                self._transform_assistant = _transform_wrapper

            elif nparams == 3:
                fn = cast(
                    Union[
                        TransformAssistantResponseChunk,
                        TransformAssistantResponseChunkAsync,
                    ],
                    fn,
                )
                self._transform_assistant = _utils.wrap_async(fn)
            else:
                raise Exception(
                    "A @transform_assistant_response function must take 1 or 3 arguments"
                )

        if fn is None:
            return _set_transform
        else:
            return _set_transform(fn)

    async def _transform_message(
        self,
        message: ChatMessage,
        chunk: ChunkOption = False,
        chunk_content: str = "",
    ) -> StoredMessage | None:
        res = self._as_stored_message(message)

        if (
            message.role == "assistant"
            and self._transform_assistant is not None
        ):
            content = await self._transform_assistant(
                message.content,
                chunk_content,
                chunk == "end" or chunk is False,
            )
        else:
            return res

        if content is None:
            return None

        return StoredMessage.from_chat_message(
            ChatMessage(content=content, role=res.role),
            html_deps=res.html_deps,
        )

    def _needs_transform(self, message: ChatMessage) -> bool:
        return (
            message.role == "assistant"
            and self._transform_assistant is not None
        )

    def _serialize_html_deps(
        self, deps: list[HTMLDependency] | None
    ) -> list[SerializedDep] | None:
        if not deps:
            return None
        if self._session is None:
            return None
        processed = self._session._process_ui(TagList(*deps))
        return cast(list[SerializedDep], processed["deps"])

    def _as_stored_message(
        self,
        message: StoredMessage | ChatMessage,
    ) -> StoredMessage:
        if isinstance(message, StoredMessage):
            return message

        html_deps = self._serialize_html_deps(message.html_deps)
        return StoredMessage.from_chat_message(message, html_deps=html_deps)

    def _store_message(
        self,
        message: StoredMessage | ChatMessage,
    ) -> None:
        from shiny import reactive

        message = self._as_stored_message(message)

        with reactive.isolate():
            messages = self._messages()

        self._messages.set((*messages, message))
        if message.role == "user":
            self._latest_user_input.set(message)

    def user_input(self) -> str | None:
        """
        Reactively read the user's message.

        Returns
        -------
        str | None
            The user input message.

        Note
        ----
        Most users shouldn't need to use this method directly since the last item in
        `.messages()` contains the most recent user input. It can be useful for:

          1. Taking a reactive dependency on the user's input outside of a `.on_user_submit()` callback.
          2. Maintaining message state separately from `.messages()`.

        """
        msg = self._latest_user_input()
        if msg is None:
            return None
        return str(msg.content)

    def _user_input(self) -> str:
        id = self.user_input_id
        return cast(str, self._session.input[id]())

    def _slash_command_input(self) -> dict[str, Any]:
        return self._session.input[self._slash_command_id]()

    def update_user_input(
        self,
        *,
        value: str | None = None,
        placeholder: str | None = None,
        submit: bool = False,
        focus: bool = False,
    ):
        """
        Update the user input.

        Parameters
        ----------
        value
            The value to set the user input to.
        placeholder
            The placeholder text for the user input.
        submit
            Whether to automatically submit the text for the user. Requires `value`.
        focus
            Whether to move focus to the input element. Requires `value`.
        """

        if value is None and (submit or focus):
            raise ValueError(
                "An input `value` must be provided when `submit` or `focus` are `True`."
            )

        action: ChatAction = {"type": "update_input"}
        if value is not None:
            action["value"] = value
        if placeholder is not None:
            action["placeholder"] = placeholder
        if submit:
            action["submit"] = submit
        if focus:
            action["focus"] = focus

        msg: dict[str, object] = {"id": self.id, "action": action}
        self._session._send_message_sync({"custom": {"shinyChatMessage": msg}})

    def set_user_message(self, value: str):
        """
        Deprecated. Use `update_user_input(value=value)` instead.
        """
        from shiny._deprecated import warn_deprecated

        warn_deprecated(
            "set_user_message() is deprecated. Use update_user_input(value=value) instead."
        )

        self.update_user_input(value=value)

    async def clear_messages(self, *, greeting: bool = False):
        """
        Clear all chat messages.

        Parameters
        ----------
        greeting
            If ``True``, also clears the greeting in addition to conversation
            messages. Clearing the greeting causes the ``{id}_greeting_requested``
            input to fire again (if the chat is visible with no greeting and no
            messages), enabling a regenerate pattern: clear the greeting, then
            react to the request to generate a new one via
            :meth:`~shinychat.Chat.set_greeting`.
        """
        self._messages.set(())
        action: ClearAction = {"type": "clear"}
        if greeting:
            action["greeting"] = True
        await self._send_action(action)

    async def set_greeting(
        self,
        greeting: "str | HTML | Tag | TagList | ChatGreeting | None",
    ) -> None:
        """
        Set or clear the chat greeting.

        A greeting is displayed at the top of the chat before any conversation messages.
        It can be static content, streaming content from an async iterator, or ``None``
        to remove an existing greeting.

        If the greeting has already been dismissed, calling this method updates the
        greeting content but does not make it visible again. To show a new greeting
        after dismissal, first clear the chat with
        ``await chat.clear_messages(greeting=True)``.

        Parameters
        ----------
        greeting
            The greeting content. Can be:

            * ``None``: clears the current greeting entirely (distinct from dismissal).
              Use this before setting a new greeting when implementing a regenerate
              pattern.
            * A markdown string, :class:`~htmltools.HTML`, :class:`~htmltools.Tag`, or
              :class:`~htmltools.TagList`: displayed as a stand-alone greeting.
            * A :func:`~shinychat.chat_greeting` object with options such as
              ``dismissible``.
            * A :func:`~shinychat.chat_greeting` wrapping an
              :class:`~typing.AsyncIterable` of strings: streams the greeting content
              chunk-by-chunk.

        Notes
        -----
        When no greeting is set and the chat is visible with no messages, an input
        named ``{id}_greeting_requested`` fires (where ``{id}`` is the chat's ID).
        Use ``@reactive.event(input.{id}_greeting_requested)`` to generate a greeting
        on demand. This input fires on first load and again after
        :meth:`~shinychat.Chat.clear_messages` is called with ``greeting=True``.

        Examples
        --------
        Static greeting (stand-alone, dismissible by default):

        ```python
        @reactive.effect
        async def _():
            await chat.set_greeting("## Welcome!\\n\\nHow can I help you today?")
        ```

        Static greeting with custom options:

        ```python
        from shinychat import chat_greeting

        @reactive.effect
        async def _():
            greeting = chat_greeting(
                "## Welcome!",
                dismissible=True,
            )
            await chat.set_greeting(greeting)
        ```

        Streaming greeting from an async iterator:

        ```python
        @reactive.effect
        async def _():
            async def token_stream():
                for token in ["Hello", " there", "!"]:
                    yield token

            await chat.set_greeting(chat_greeting(token_stream()))
        ```

        LLM-generated greeting using ``greeting_requested``:

        ```python
        import chatlas
        from shinychat import Chat, chat_greeting

        chat_model = chatlas.ChatOpenAI(model="gpt-4o")
        chat = Chat(id="chat")

        @reactive.effect
        @reactive.event(input.chat_greeting_requested)
        async def _():
            response = await chat_model.stream_async(
                "Write a short, friendly welcome message."
            )
            await chat.set_greeting(chat_greeting(response))
        ```

        Regenerate pattern (clear and re-request):

        ```python
        @reactive.effect
        @reactive.event(input.regenerate)
        async def _():
            await chat.clear_messages(greeting=True)

        # greeting_requested fires again after clear_messages(greeting=True),
        # so the LLM-generated greeting handler above will run again.
        ```

        Clear the greeting (e.g., before setting a new one):

        ```python
        await chat.set_greeting(None)
        ```
        """
        if greeting is None:
            await self._send_action({"type": "greeting_clear"})
            return

        if not isinstance(greeting, ChatGreeting):
            greeting = chat_greeting(greeting)

        options: GreetingOptions = {"dismissible": greeting.dismissible}
        html_deps = self._serialize_html_deps(greeting.html_deps) if greeting.html_deps else None

        content = greeting.content
        if isinstance(content, AsyncIterable):
            start_action: ChatAction = {
                "type": "greeting_start",
                "content": "",
                "content_type": greeting.content_type,
                "options": options,
            }
            await self._send_action(start_action)
            try:
                async for chunk in content:
                    chunk_action: ChatAction = {
                        "type": "greeting_chunk",
                        "content": chunk,
                        "operation": "append",
                    }
                    await self._send_action(chunk_action)
            finally:
                await self._send_action({"type": "greeting_end"})
        else:
            action: ChatAction = {
                "type": "greeting",
                "content": str(content),
                "content_type": greeting.content_type,
                "options": options,
            }
            await self._send_action(action, html_deps)

    def destroy(self):
        """
        Destroy the chat instance.
        """
        self._destroy_effects()
        self._destroy_bookmarking()

    def _destroy_effects(self):
        for x in self._effects:
            x.destroy()
        self._effects.clear()

    def _destroy_bookmarking(self):
        if not self._cancel_bookmarking_callbacks:
            return

        self._cancel_bookmarking_callbacks()
        self._cancel_bookmarking_callbacks = None

    async def _remove_loading_message(self):
        await self._send_action({"type": "remove_loading"})

    async def _hide_tool_request(self, request_id: str) -> None:
        action: ChatAction = {
            "type": "hide_tool_request",
            "requestId": request_id,
        }
        await self._send_action(action)

    async def _send_action(
        self,
        action: ChatAction,
        html_deps: list[SerializedDep] | None = None,
    ):
        envelope: dict[str, object] = {
            "id": self.id,
            "action": action,
        }
        if html_deps:
            envelope["html_deps"] = html_deps
        await self._session.send_custom_message("shinyChatMessage", envelope)

    def enable_bookmarking(
        self,
        client: "ClientWithState | chatlas.Chat[Any, Any]",
        /,
        *,
        bookmark_on: Optional[Literal["response"]] = "response",
    ) -> CancelCallback:
        """
        Enable bookmarking for the chat instance.

        This method registers `on_bookmark` and `on_restore` hooks on `session.bookmark`
        (:class:`shiny.bookmark.Bookmark`) to save/restore chat state on both the `Chat`
        and `client=` instances. In order for this method to actually work correctly, a
        `bookmark_store=` must be specified in `shiny.App()`.

        Parameters
        ----------
        client
            The chat client instance to use for bookmarking. This can be a Chat model
            provider from [chatlas](https://posit-dev.github.io/chatlas/), or more
            generally, an instance following the `ClientWithState` protocol.
        bookmark_on
            The event to trigger the bookmarking on. Supported values include:

            - `"response"` (the default): a bookmark is triggered when the assistant is done responding.
            - `None`: no bookmark is triggered

            When this method triggers a bookmark, it also updates the URL query string to reflect the bookmarked state.


        Raises
        ------
        ValueError
            If the Shiny App does have bookmarking enabled.

        Returns
        -------
        :
            A callback to cancel the bookmarking hooks.
        """
        from shiny import reactive
        from shiny.session import get_current_session

        session = get_current_session()
        if session is None or session.is_stub_session():
            return BookmarkCancelCallback(lambda: None)

        resolved_bookmark_id_str = str(self.id)
        resolved_bookmark_id_msgs_str = resolved_bookmark_id_str + "--msgs"
        get_state: Callable[[], Awaitable[Jsonifiable]]
        set_state: Callable[[Jsonifiable], Awaitable[None]]

        # Retrieve get_state/set_state functions from the client
        if isinstance(client, ClientWithState):
            # Do client with state stuff here
            get_state = _utils.wrap_async(client.get_state)
            set_state = _utils.wrap_async(client.set_state)

        elif is_chatlas_chat_client(client):
            get_state = get_chatlas_state(client)
            set_state = set_chatlas_state(client)

        else:
            raise ValueError(
                "Bookmarking requires a client that supports "
                "`async def get_state(self) -> shiny.types.Jsonifiable` (which returns an object that can be used when bookmarking to save the state of the `client=`) and "
                "`async def set_state(self, value: Jsonifiable)` (which should restore the `client=`'s state given the `state=`)."
            )

        # Reset prior bookmarking hooks
        self._destroy_bookmarking()

        # Must use `root_session` as the id is already resolved. :-/
        # Using a proxy session would double-encode the proxy-prefix
        root_session = session.root_scope()
        root_session.bookmark.exclude.append(self.id + "_user_input")

        # ###########
        # Bookmarking

        if bookmark_on is not None:
            # When ever the bookmark is requested, update the query string (indep of store type)
            @root_session.bookmark.on_bookmarked
            async def _(url: str):
                await session.bookmark.update_query_string(url)

        if bookmark_on == "response":

            @reactive.effect
            @reactive.event(
                self.messages, ignore_init=True
            )
            async def _():
                messages = self.messages()

                if len(messages) == 0:
                    return

                last_message = messages[-1]

                if last_message.get("role") == "assistant":
                    await session.bookmark()

        ###############
        # Client Bookmarking

        @root_session.bookmark.on_bookmark
        async def _on_bookmark_client(state: BookmarkState):
            if resolved_bookmark_id_str in state.values:
                raise ValueError(
                    f'Bookmark value with id (`"{resolved_bookmark_id_str}"`) already exists.'
                )

            with reactive.isolate():
                state.values[resolved_bookmark_id_str] = await get_state()

        @root_session.bookmark.on_restore
        async def _on_restore_client(state: RestoreState):
            if resolved_bookmark_id_str not in state.values:
                return

            # Retrieve the chat turns from the bookmark state
            info = state.values[resolved_bookmark_id_str]
            await set_state(info)

        ###############
        # UI Bookmarking

        @root_session.bookmark.on_bookmark
        def _on_bookmark_ui(state: BookmarkState):
            if resolved_bookmark_id_msgs_str in state.values:
                raise ValueError(
                    f'Bookmark value with id (`"{resolved_bookmark_id_msgs_str}"`) already exists.'
                )

            with reactive.isolate():
                # This does NOT contain the `chat.ui(messages=)` values.
                # When restoring, the `chat.ui(messages=)` values will need to be kept
                # and the `ui.Chat(messages=)` values will need to be reset
                state.values[resolved_bookmark_id_msgs_str] = self._messages_for_bookmark()

        # Attempt to stop the initialization of the `ui.Chat(messages=)` messages
        self._init_chat.destroy()

        @root_session.bookmark.on_restore
        async def _on_restore_ui(state: RestoreState):
            # Do not call `self.clear_messages()` as it will clear the
            # `chat.ui(messages=)` in addition to the `self.messages()`
            # (which is not what we want).

            # We always want to keep the `chat.ui(messages=)` values
            # and `self.messages()` are never initialized due to
            # calling `self._init_chat.destroy()` above

            if resolved_bookmark_id_msgs_str not in state.values:
                # If no messages to restore, display the `__init__(messages=)` messages
                await self._append_init_messages()
                return

            msgs: list[Any] = state.values[resolved_bookmark_id_msgs_str]
            if not isinstance(msgs, list):
                raise ValueError(
                    f"Bookmark value with id (`{resolved_bookmark_id_msgs_str}`) must be a list of messages."
                )

            for message_dict in msgs:
                await self._restore_bookmark_message(message_dict)

        def _cancel_bookmarking():
            _on_bookmark_client()
            _on_bookmark_ui()
            _on_restore_client()
            _on_restore_ui()

        # Store the callbacks to be able to destroy them later
        self._cancel_bookmarking_callbacks = _cancel_bookmarking

        return BookmarkCancelCallback(_cancel_bookmarking)


class ChatExpress(Chat):
    def ui(
        self,
        *,
        messages: Optional[
            Iterable[str | TagChild | ChatMessageDict | ChatMessage | Any]
        ] = None,
        greeting: Optional[Union[str, HTML, Tag, TagList, ChatGreeting]] = None,
        placeholder: str = "Enter a message...",
        width: "CssUnit" = "min(680px, 100%)",
        height: "CssUnit" = "auto",
        fill: bool = True,
        icon_assistant: HTML | Tag | TagList | None = None,
        enable_cancel: "bool | MISSING_TYPE" = MISSING,
        submit_key: 'Literal["enter", "enter+modifier"]' = "enter",
        footer: Optional[TagChild] = None,
        **kwargs: TagAttrValue,
    ) -> Tag:
        """
        Create a UI element for this `Chat`.

        Parameters
        ----------
        messages
            A sequence of messages to display in the chat. Each message can be either a
            string or a dictionary with `content` and `role` keys. The `content` key
            should contain the message text, and the `role` key can be "assistant" or
            "user".
        greeting
            An optional greeting to display at the top of the chat before any conversation
            messages. Can be a markdown string or a :func:`~shinychat.chat_greeting`
            object.
        placeholder
            Placeholder text for the chat input.
        width
            The width of the UI element.
        height
            The height of the UI element.
        fill
            Whether the chat should vertically take available space inside a fillable
            container.
        icon_assistant
            The icon to use for the assistant chat messages. Can be a HTML or a tag in
            the form of :class:`~htmltools.HTML` or :class:`~htmltools.Tag`. If `None`,
            a default robot icon is used.
        enable_cancel
            Whether to show a stop button during streaming that allows the user to
            cancel the in-progress response. When ``True``, the chat UI shows a stop
            button in place of the send button while streaming. You must observe
            ``input.<id>_cancel`` on the server and call ``ctrl.cancel()`` on a
            chatlas ``StreamController`` to actually stop the stream. Defaults to
            ``True`` when a ``client=`` was provided to :class:`~shinychat.Chat`,
            ``False`` otherwise.
        submit_key
            Controls which key combination submits the chat message:

            - ``"enter"`` (default): Enter submits, Shift+Enter adds a newline.
            - ``"enter+modifier"``: Ctrl+Enter (Cmd+Enter on Mac) submits,
              plain Enter adds a newline.
        footer
            Optional HTML content to display below the chat input.
            This can be any HTML content (tags, tag lists, or strings).
            Useful for adding disclaimers, attribution, or other information.
            The footer text is styled slightly smaller and lighter than body text
            by default. Customize with CSS properties ``--shiny-chat-footer-font-size``
            and ``--shiny-chat-footer-color`` on the chat container or footer element.
        kwargs
            Additional attributes for the chat container element.
        """

        # Don't resolve a default here: when `enable_cancel` is unset, a
        # `client=` enables the stop button at runtime via `update_cancel`
        # (see `_setup_client`). Forward the tri-state and let the client decide.
        return chat_ui(
            id=self.id,
            messages=messages,
            greeting=greeting,
            placeholder=placeholder,
            width=width,
            height=height,
            fill=fill,
            icon_assistant=icon_assistant,
            enable_cancel=enable_cancel,
            submit_key=submit_key,
            footer=footer,
            **kwargs,
        )

    def enable_bookmarking(
        self,
        client: "ClientWithState | chatlas.Chat[Any, Any]",
        /,
        *,
        bookmark_store: "Optional[BookmarkStore]" = None,
        bookmark_on: Optional[Literal["response"]] = "response",
    ) -> CancelCallback:
        """
        Enable bookmarking for the chat instance.

        This method registers `on_bookmark` and `on_restore` hooks on `session.bookmark`
        (:class:`shiny.bookmark.Bookmark`) to save/restore chat state on both the `Chat`
        and `client=` instances. In order for this method to actually work correctly, a
        `bookmark_store=` must be specified in `shiny.express.app_opts()`.

        Parameters
        ----------
        client
            The chat client instance to use for bookmarking. This can be a Chat model
            provider from [chatlas](https://posit-dev.github.io/chatlas/), or more
            generally, an instance following the `ClientWithState` protocol.
        bookmark_store
            A convenience parameter to set the `shiny.express.app_opts(bookmark_store=)`
            which is required for bookmarking (and `.enable_bookmarking()`). If `None`,
            no value will be set.
        bookmark_on
            The event to trigger the bookmarking on. Supported values include:

            - `"response"` (the default): a bookmark is triggered when the assistant is done responding.
            - `None`: no bookmark is triggered

            When this method triggers a bookmark, it also updates the URL query string to reflect the bookmarked state.

        Raises
        ------
        ValueError
            If the Shiny App does have bookmarking enabled.

        Returns
        -------
        :
            A callback to cancel the bookmarking hooks.
        """

        if bookmark_store is not None:
            from shiny.express import app_opts

            app_opts(bookmark_store=bookmark_store)

        return super().enable_bookmarking(client, bookmark_on=bookmark_on)


def chat_ui(
    id: str,
    *,
    messages: Optional[
        Iterable[str | TagChild | ChatMessageDict | ChatMessage | Any]
    ] = None,
    greeting: Optional[Union[str, HTML, Tag, TagList, ChatGreeting]] = None,
    placeholder: str = "Enter a message...",
    width: "CssUnit" = "min(680px, 100%)",
    height: "CssUnit" = "auto",
    fill: bool = True,
    icon_assistant: Optional[HTML | Tag | TagList] = None,
    enable_cancel: "bool | MISSING_TYPE" = MISSING,
    submit_key: 'Literal["enter", "enter+modifier"]' = "enter",
    footer: Optional[TagChild] = None,
    **kwargs: TagAttrValue,
) -> Tag:
    """
    UI container for a chat component (Shiny Core).

    This function is for locating a :class:`~shiny.ui.Chat` instance in a Shiny Core
    app. If you are using Shiny Express, use the :method:`~shiny.ui.Chat.ui` method
    instead.

    Parameters
    ----------
    id
        A unique identifier for the chat UI.
    messages
        A sequence of messages to display in the chat. A given message can be one of the
        following:

        * A string, which is interpreted as markdown and rendered to HTML on the client.
            * To prevent interpreting as markdown, mark the string as
              :class:`~shiny.ui.HTML`.
        * A UI element (specifically, a :class:`~shiny.ui.TagChild`).
            * This includes :class:`~shiny.ui.TagList`, which take UI elements
              (including strings) as children. In this case, strings are still
              interpreted as markdown as long as they're not inside HTML.
        * A dictionary with `content` and `role` keys. The `content` key can contain a
          content as described above, and the `role` key can be "assistant" or "user".
        * More generally, any type registered with :func:`shinychat.message_content`.

        **NOTE:** content may include specially formatted **input suggestion** links
        (see :method:`~shiny.ui.Chat.append_message` for more info).
    greeting
        An optional greeting to display at the top of the chat before any conversation
        messages. Can be a markdown string or a :func:`~shinychat.chat_greeting` object.
        For a dynamic or streaming greeting, use :meth:`~shinychat.Chat.set_greeting`
        from the server instead.

        When no greeting is set and the chat is visible with no messages, an input
        named ``{id}_greeting_requested`` fires. Use this input with
        ``@reactive.event(input.{id}_greeting_requested)`` to generate a greeting
        on demand from the server. It fires again after
        :meth:`~shinychat.Chat.clear_messages` is called with ``greeting=True``.
    placeholder
        Placeholder text for the chat input.
    width
        The width of the chat container.
    height
        The height of the chat container.
    fill
        Whether the chat should vertically take available space inside a fillable container.
    icon_assistant
            The icon to use for the assistant chat messages. Can be a HTML or a tag in
            the form of :class:`~htmltools.HTML` or :class:`~htmltools.Tag`. If `None`,
            a default robot icon is used.
    enable_cancel
        Whether to show a stop button during streaming that allows the user to
        cancel the in-progress response. When ``True``, the chat UI shows a stop
        button in place of the send button while streaming. You must observe
        ``input.<id>_cancel`` on the server and call ``ctrl.cancel()`` on a
        chatlas ``StreamController`` to actually stop the stream. When left
        unset (the default), a chat driven by a ``client=`` enables the stop
        button automatically; otherwise it stays hidden. Passing an explicit
        ``True``/``False`` always wins over that automatic behavior.
    submit_key
        Controls which key combination submits the chat message:

        - ``"enter"`` (default): Enter submits, Shift+Enter adds a newline.
        - ``"enter+modifier"``: Ctrl+Enter (Cmd+Enter on Mac) submits,
          plain Enter adds a newline.
    footer
        Optional HTML content to display below the chat input.
        This can be any HTML content (tags, tag lists, or strings).
        Useful for adding disclaimers, attribution, or other information.
        The footer text is styled slightly smaller and lighter than body text
        by default. Customize with CSS properties ``--shiny-chat-footer-font-size``
        and ``--shiny-chat-footer-color`` on the chat container or footer element.
    kwargs
        Additional attributes for the chat container element.
    """
    from shiny.module import resolve_id
    from shiny.ui.css import as_css_unit
    from shiny.ui.fill import as_fill_item, as_fillable_container

    id = resolve_id(id)

    icon_attr = None
    if icon_assistant is not None:
        icon_attr = str(icon_assistant)

    icon_deps = None
    if isinstance(icon_assistant, (Tag, TagList)):
        icon_deps = icon_assistant.get_dependencies()

    message_tags: list[Tag] = []
    if messages is None:
        messages = []
    for x in messages:
        msg = message_content(x)
        message_tags.append(
            Tag(
                "shiny-chat-message",
                *msg.html_deps,
                content=msg.content,
                icon=icon_attr,
                data_role=msg.role,
            )
        )

    footer_tag = None
    if footer is not None:
        footer_tag = Tag("shiny-chat-footer", footer)

    # Tri-state attribute: omitted = "no explicit preference" (lets a `client=`
    # auto-enable the stop button at runtime), "true"/"false" = explicit choice
    # that the client honors over any `update_cancel` message.
    enable_cancel_attr: Optional[str] = (
        None
        if isinstance(enable_cancel, MISSING_TYPE)
        else ("true" if enable_cancel else "false")
    )

    greeting_attr: Optional[str] = None
    greeting_deps: list[HTMLDependency] = []
    if greeting is not None:
        if not isinstance(greeting, ChatGreeting):
            greeting = chat_greeting(greeting)

        if hasattr(greeting.content, "__aiter__"):
            raise ValueError(
                "An async iterator is not valid as a static `greeting` in `chat_ui()`. "
                "Use `await chat.set_greeting()` from the server to stream a greeting."
            )

        greeting_payload: dict[str, object] = {
            "content": greeting.content,
            "content_type": greeting.content_type,
            "options": {"dismissible": greeting.dismissible},
        }
        greeting_attr = json.dumps(greeting_payload)
        greeting_deps = greeting.html_deps

    res = Tag(
        "shiny-chat-container",
        *greeting_deps,
        Tag("shiny-chat-messages", *message_tags),
        Tag(
            "shiny-chat-input",
            id=f"{id}_user_input",
            placeholder=placeholder,
        ),
        footer_tag,
        shinychat_dependency(),
        icon_deps,
        {
            "style": css(
                width=as_css_unit(width),
                height=as_css_unit(height),
            )
        },
        id=id,
        placeholder=placeholder,
        fill=fill,
        greeting=greeting_attr,
        enable_cancel=enable_cancel_attr,
        # Also include icon on the parent so that when messages are dynamically added,
        # we know the default icon has changed
        icon_assistant=icon_attr,
        submit_key=submit_key if submit_key != "enter" else None,
        **kwargs,
    )

    if fill:
        res = as_fillable_container(as_fill_item(res))

    return res


class MessageStream:
    """
    An object to yield from a `.message_stream_context()` context manager.
    """

    def __init__(self, chat: Chat, stream_id: str):
        self._chat = chat
        self._stream_id = stream_id

    async def replace(self, message_chunk: Any):
        """
        Replace the content of the stream with new content.

        Parameters
        -----------
        message_chunk
            The new content to replace the current content.
        """
        await self._chat._append_message_chunk(
            message_chunk,
            operation="replace",
            stream_id=self._stream_id,
        )

    async def append(self, message_chunk: Any):
        """
        Append a message chunk to the stream.

        Parameters
        -----------
        message_chunk
            A message chunk to append to this stream
        """
        await self._chat._append_message_chunk(
            message_chunk,
            stream_id=self._stream_id,
        )


def is_tool_result(val: object) -> "TypeGuard[chatlas.ContentToolResult]":
    try:
        from chatlas.types import ContentToolResult

        return isinstance(val, ContentToolResult)
    except ImportError:
        return False


CHAT_INSTANCES: WeakValueDictionary[str, Chat] = WeakValueDictionary()
