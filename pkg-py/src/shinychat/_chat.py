from __future__ import annotations

import asyncio
import inspect
import json
import os
import re
import warnings
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
    NamedTuple,
    Optional,
    Sequence,
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
)
from pydantic import ValidationError

from . import _utils
from ._attachments import (
    Attachment,
    attachment_to_content,
    resolve_attachment_attrs,
    resolve_max_attachment_size,
)
from ._chat_bookmark import (
    BookmarkCancelCallback,
    CancelCallback,
    ClientWithState,
    get_chatlas_state,
    is_chatlas_chat_client,
    set_chatlas_state,
)
from ._chat_normalize import (
    normalize_message,
    normalize_message_chunk,
)
from ._chat_segments import segments_content, segments_deps
from ._chat_transcript import ChatTranscript, StreamCandidate
from ._chat_types import (
    ChatAction,
    ChatGreeting,
    ChatMessage,
    ChatMessageDict,
    ClearAction,
    ContentSegment,
    GreetingAction,
    GreetingOptions,
    GreetingSnapshot,
    GreetingSnapshotModel,
    MessagePayload,
    SerializedDep,
    SlashCommandDef,
    StoredMessage,
    StoredSegment,
    chat_greeting,
)
from ._history import ChatHistory, HistoryOptions
from ._html_deps_py_shiny import shinychat_dependency
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
    from ._input_handler import UserInputValue


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
    "UserInput",
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
UserSubmitFunction2 = Union[
    Callable[[str, list["Attachment"]], None],
    Callable[[str, list["Attachment"]], Awaitable[None]],
]
UserSubmitFunction = Union[
    UserSubmitFunction0,
    UserSubmitFunction1,
    UserSubmitFunction2,
]


@dataclass(frozen=True)
class SlashCommandRegistration:
    handler: UserSubmitFunction | None
    takes_args: bool
    definition: SlashCommandDef


class UserInput(NamedTuple):
    text: str
    attachments: list[Attachment]


ChunkOption = Literal["start", "end", True, False]


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
        streaming, cancellation, and conversation history are wired up
        automatically. This includes registering an
        :meth:`~shinychat.Chat.on_user_submit` callback that streams the
        client's response to each user message, so you don't need to write one
        yourself. Any additional ``@chat.on_user_submit`` handlers you register
        still run, in addition to (not in place of) this one.
        The resulting :attr:`chat.client` exposes a
        :class:`~shinychat.types.ChatClient` wrapper for swapping models
        (``.set()``) and resetting the conversation (``.clear()``).
    history
        Conversation history configuration. ``True`` (the default) enables
        history with default settings; ``False`` disables it; pass a
        :class:`~shinychat.types.HistoryOptions` instance to customise
        restore behaviour, storage, user identity, or titling. Only takes
        effect when a ``client=`` is also provided.
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
        history: "bool | HistoryOptions" = True,
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

        self._message_lock = asyncio.Lock()

        # Keep track of effects so we can destroy them when the chat is destroyed
        self._effects: list["Effect_"] = []
        history_config = history if isinstance(history, HistoryOptions) else None
        self._history_enabled: bool = history is not False
        self.history: ChatHistory = ChatHistory(self, config=history_config)
        self._cancel_bookmarking_callbacks: CancelCallback | None = None
        self._greeting_snapshot: GreetingSnapshot | None = None

        # Initialize chat state and user input effect
        from shiny import reactive
        from shiny.session import session_context

        with session_context(self._session):
            self._transcript_version: reactive.Value[int] = reactive.Value(0)

            def notify_transcript_change() -> None:
                with reactive.isolate():
                    version = self._transcript_version()
                self._transcript_version.set(version + 1)

            self._transcript = ChatTranscript(
                on_change=notify_transcript_change
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

            @reactive.effect(priority=9999)
            @reactive.event(self._user_input)
            async def _on_user_input():
                try:
                    text, attachments = self._user_input()
                    msg = ChatMessage(
                        content=text,
                        role="user",
                        attachments=attachments,
                    )
                    await self._store_message(msg)
                except Exception as e:
                    await self._raise_exception(e)

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
                try:
                    if echo:
                        full_text = f"/{command} {user_text}".rstrip()
                        msg = ChatMessage(content=full_text, role="user")
                        await self._store_message(msg)
                    cmds = self._slash_commands()
                    reg = cmds.get(command) if cmds else None
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
        from shiny.module import ResolvedId
        from shiny.session import session_context

        from ._chat_client import ChatClient

        chat_client = ChatClient(
            chat=self,
            client=client,
        )
        self.client = chat_client

        controller = StreamController()
        cancel_input_id = ResolvedId(f"{self.id}_cancel")

        # Match the rest of `__init__`: create these effects under the chat's
        # own session so they attach correctly even when `Chat(...)` is
        # constructed outside that session's reactive context.
        with session_context(self._session):

            @self.on_user_submit
            async def _on_user_submit(user_input: str, attachments: list[Attachment]) -> None:
                contents = [attachment_to_content(a) for a in attachments]
                try:
                    response = await chat_client.value.stream_async(
                        user_input,
                        *contents,
                        content="all",
                        controller=controller,
                    )
                except BaseException as error:
                    await self._settle_response(
                        self.history._response_settled,
                        response_error=error,
                    )
                    raise
                await self._start_message_stream(
                    response,
                    on_settled=self.history._response_settled,
                )

            # A `client=` wires up cancellation, so enable the stop button
            # without requiring `enable_cancel=True` in `chat_ui()`. It only
            # surfaces while streaming, so sending this once at session start
            # (the effect has no reactive dependencies) is enough.
            @reactive.effect
            async def _enable_cancel_ui() -> None:
                await self._send_action(
                    {"type": "update_cancel", "enable_cancel": True}
                )

            # A `client=` (chatlas) accepts image content, so enable the
            # attachment affordance without requiring `allow_attachments=True`
            # in `chat_ui()`.
            @reactive.effect
            async def _enable_upload_ui() -> None:
                await self._send_action(
                    {"type": "update_upload", "enable_upload": True}
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
            self._effects.append(_enable_upload_ui)
            self._effects.append(_on_cancel)
            self._effects.append(_on_stream_complete)

            if self._history_enabled:
                self.history.enable()

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
        when the user submits a message. This function can take up to two optional
        arguments: the user input message (a `str`) and any attached files (a
        `list[Attachment]`, where each item exposes ``mime`` (MIME type),
        ``data_url`` (a ``data:<mime>;base64,...`` URL), and ``name``
        (the original filename) attributes).

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
                    if len(fn_params) > 2:
                        raise ValueError(
                            "An on_user_submit function should not take more than 2 arguments"
                        )
                    elif len(fn_params) == 2:
                        afunc = _utils.wrap_async(cast(UserSubmitFunction2, fn))
                        user_input = self.user_input()
                        assert user_input is not None
                        await afunc(*user_input)
                    elif len(fn_params) == 1:
                        user_input = self.user_input()
                        assert user_input is not None
                        text, _ = user_input
                        afunc = _utils.wrap_async(cast(UserSubmitFunction1, fn))
                        await afunc(text)
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
            A tuple of chat messages. The ``attachments`` field, when present,
            contains :class:`~shinychat.Attachment` objects. These are Pydantic
            models, so call ``.model_dump()`` on each one before passing them to
            ``json.dumps()`` or any other JSON serializer.
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

        self._transcript_version()
        messages = self._transcript.read()

        res: list[ChatMessageDict] = []
        for m in messages:
            chat_msg = ChatMessageDict(content=str(m.content), role=m.role)
            if m.html_deps:
                chat_msg["html_deps"] = m.html_deps
            if m.attachments:
                chat_msg["attachments"] = m.attachments
            res.append(chat_msg)

        return tuple(res)

    async def append_message(
        self,
        message: Any,
        *,
        icon: HTML | Tag | TagList | bool | None = None,
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
            :func:`~shiny.ui.img` tag) or a string of HTML. Pass ``False`` to remove
            the icon for this message, or ``True`` to use the default icon.

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

        :::{.callout-note title="Asides"}
        An aside is a small pill that appears at the end of the paragraph or
        list item it's attached to, showing a popover on hover, click, or
        keyboard focus. Create one by writing (or prompting an LLM to write) an
        inline `<shiny-aside>` tag anywhere in a block's markdown; the tag's
        content becomes the popover body:

        * `<shiny-aside label="a source name" url="https://...">markdown shown in the popover</shiny-aside>`

        `label` controls the text on the identity chip. A safe `url` makes the
        source heading in the popover a link. It also supplies a derived favicon
        unless `icon` overrides it. Without a `label`, the aside falls back to
        a plain numbered marker. The body is ordinary markdown: inline for a
        one-liner, or — by separating it with blank lines — a rich block body
        (paragraphs, lists, code) shown in the popover. Labeled asides in the
        same paragraph or list item collapse into one pill, with each aside kept
        as a separate popover page. Each unlabeled aside remains a separate
        numbered pill. The grouped pill shows a `+N` overflow count only when
        its labeled asides have different labels. Asides that share one label
        use a single face with no count.

        `grounded-span` identifies the answer text that is related to an aside.
        Its value must exactly match text before the tag in the same paragraph
        or list item. When the popover opens, shinychat highlights the most
        recent match. If the value does not match, no text is highlighted.

        Long content wraps and scrolls within the viewport. The popover keeps
        the nearest scoped Bootstrap theme. In a paged popover, page changes
        are announced to assistive technology without repeating the body.

        The favicon is fetched at render time from a third-party service
        (DuckDuckGo's icon service), which receives the cited site's hostname.
        To avoid that request — for privacy, or for offline/air-gapped
        deployments — set the ``SHINYCHAT_ASIDE_FAVICON`` environment variable
        to ``false``. You can still set `icon` to a URL you control; an
        explicit `icon` bypasses the lookup entirely.

        **Examples:**

        * A labeled aside with a grounded span and a one-line body:
          `Hub motors are cheaper<shiny-aside label="eBicycles" url="https://ebicycles.example/hub-vs-mid-drive" grounded-span="Hub motors are cheaper">[Hub Motor vs. Mid-Drive Motor Differences Explained](https://ebicycles.example/hub-vs-mid-drive)</shiny-aside>, and ideal for flatter terrain.`
        * Two asides cited in the same sentence collapse into a single pill
          — the first source's label becomes the face, with a "+1" overflow:
          `...<shiny-aside label="eBicycles" url="https://ebicycles.example">...</shiny-aside><shiny-aside label="WIRED" url="https://wired.example">...</shiny-aside>...`
        * A label-less aside with a rich block body (a blank line starts a
          block body instead of an inline one), falling back to a plain
          numbered pill:
          `Battery quality matters more than raw power<shiny-aside>\n\n**Methodology**\n\n- 40 commuter e-bike models\n- released in 2024\n\n</shiny-aside>`
        :::

        :::{.callout-note title="Streamed messages"}
        Use `.append_message_stream()` instead of this method when `stream=True` (or
        similar) is specified in model's completion method.
        :::
        """
        async with self._message_lock:
            await self._append_message_locked(message, icon=icon)

    async def _append_message_locked(
        self,
        message: Any,
        *,
        icon: HTML | Tag | TagList | None = None,
    ) -> bool:
        msg = normalize_message(message)
        msg = await self._transform_message(msg)
        if msg is None:
            return True

        stored = self._as_stored_message(msg)

        async def send() -> None:
            await self._send_append_message(
                message=stored,
                chunk=False,
                icon=icon,
            )

        await self._transcript.append(stored, send=send)
        self._note_latest_user_input(stored)
        return True

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
        async with self._message_lock:
            context = self._transcript.enter_context()
            stream_id = context.stream_id
            is_root_stream = stream_id is None
            try:
                if is_root_stream:
                    stream_id = _utils.private_random_id()
                    await self._append_message_chunk_locked(
                        "", chunk="start", stream_id=stream_id
                    )
            except BaseException:
                self._transcript.exit_context(context)
                raise

        try:
            yield MessageStream(self, stream_id)
        finally:
            async with self._message_lock:
                if self._transcript.generation == context.generation:
                    self._transcript.exit_context(context)
                    if is_root_stream:
                        await self._append_message_chunk_locked(
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
        icon: HTML | Tag | TagList | bool | None = None,
    ) -> None:
        async with self._message_lock:
            await self._append_message_chunk_locked(
                message,
                chunk=chunk,
                stream_id=stream_id,
                operation=operation,
                icon=icon,
            )

    async def _append_message_chunk_locked(
        self,
        message: Any,
        *,
        chunk: Literal[True, "start", "end"] = True,
        stream_id: str,
        operation: Literal["append", "replace"] = "append",
        icon: HTML | Tag | TagList | None = None,
    ) -> bool:
        # Normalize various message types into a ChatMessage()
        msg = normalize_message_chunk(message)
        if chunk == "start":

            async def start_send() -> None:
                await self._send_append_message(
                    message=msg, chunk="start", icon=icon
                )

            await self._transcript.start(
                msg, stream_id=stream_id, send=start_send
            )
            return True

        if chunk == "end":
            # A terminal chunk can still carry real content (e.g. a direct
            # `.replace()` on the last chunk), so fold it into the active
            # segments first -- respecting checkpoint/replace semantics the
            # same way a regular chunk would -- before settling. The fold's
            # own `send` is a no-op; the wire message and settled message are
            # built once, from the folded segments, in `settle_send` below.
            async def fold_send(
                candidate: StreamCandidate,
            ) -> StoredMessage | None:
                return candidate.projection

            await self._transcript.chunk(
                msg, stream_id=stream_id, operation=operation, send=fold_send
            )

            settled_holder: list[StoredMessage] = []

            async def settle_send(candidate: StreamCandidate) -> StoredMessage:
                settled, _ = await self._resolve_stream_chunk(
                    msg,
                    segments=candidate.segments,
                    projection=candidate.projection,
                    operation=operation,
                    is_end=True,
                    icon=icon,
                )
                assert settled is not None
                settled_holder.append(settled)
                return settled

            try:
                await self._transcript.settle(
                    stream_id=stream_id, send=settle_send
                )
            except BaseException:
                self._transcript.abort(stream_id)
                raise
            self._note_latest_user_input(settled_holder[0])
            return True

        async def chunk_send(
            candidate: StreamCandidate,
        ) -> StoredMessage | None:
            _, next_projection = await self._resolve_stream_chunk(
                msg,
                segments=candidate.segments,
                projection=candidate.projection,
                operation=operation,
                is_end=False,
                icon=icon,
            )
            return next_projection

        await self._transcript.chunk(
            msg, stream_id=stream_id, operation=operation, send=chunk_send
        )
        return True

    async def _resolve_stream_chunk(
        self,
        msg: ChatMessage,
        *,
        segments: tuple[ContentSegment, ...],
        projection: StoredMessage | None,
        operation: Literal["append", "replace"],
        is_end: bool,
        icon: HTML | Tag | TagList | None,
    ) -> tuple[StoredMessage | None, StoredMessage | None]:
        """Transform, send, and resolve one stream chunk (or the terminal settle).

        Returns ``(settled, next_projection)``; ``settled`` is non-``None`` only
        when ``is_end`` is ``True``. When a mid-stream transform declines to
        update (returns ``None``), no wire message is sent and the previous
        projection is returned unchanged.
        """
        staged_segments = list(segments)
        stream_content = segments_content(staged_segments)
        if operation == "replace":
            msg.content = stream_content

        settled: StoredMessage | None = None
        next_projection = projection
        wire_message: StoredMessage | ChatMessage = msg
        chunk_flag: Literal[True, "end"] = "end" if is_end else True

        if self._needs_transform(msg):
            chunk_content = msg.content
            msg.content = stream_content
            operation = "replace"
            transformed = await self._transform_message(
                msg, chunk=chunk_flag, chunk_content=chunk_content
            )
            if transformed is None:
                if not is_end:
                    return None, projection
                settled = self._settled_stream_projection(
                    projection, staged_segments
                )
                wire_message = StoredMessage(role=msg.role, segments=[])
            else:
                next_projection = transformed
                wire_message = transformed
                if is_end:
                    settled = self._settled_stream_projection(
                        transformed, staged_segments
                    )
                    assert settled is not None
                    wire_message = settled
        elif is_end:
            settled = StoredMessage(
                role=msg.role,
                segments=[
                    StoredSegment(
                        content=segment.content,
                        content_type=segment.content_type,
                        html_deps=self._serialize_html_deps(segment.html_deps),
                    )
                    for segment in staged_segments
                ],
            )

        await self._send_append_message(
            message=wire_message,
            chunk=chunk_flag,
            operation=operation,
            icon=icon,
        )
        return settled, next_projection

    async def _abort_message_stream(self, stream_id: str) -> None:
        async with self._message_lock:
            self._transcript.abort(stream_id)

    async def append_message_stream(
        self,
        message: Iterable[Any] | AsyncIterable[Any],
        *,
        icon: HTML | Tag | bool | None = None,
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
            :func:`~shiny.ui.img` tag) or a string of HTML. Pass ``False`` to remove
            the icon for this message, or ``True`` to use the default icon.

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

        ```{.callout-note title="Asides"}
        An aside is a small pill that appears at the end of the paragraph or
        list item it's attached to, showing a popover on hover, click, or
        keyboard focus. Create one by writing (or prompting an LLM to write) an
        inline `<shiny-aside>` tag anywhere in a block's markdown; the tag's
        content becomes the popover body:

        * `<shiny-aside label="a source name" url="https://...">markdown shown in the popover</shiny-aside>`

        `label` controls the text on the identity chip. A safe `url` makes the
        source heading in the popover a link. It also supplies a derived favicon
        unless `icon` overrides it. Without a `label`, the aside falls back to
        a plain numbered marker. The body is ordinary markdown: inline for a
        one-liner, or — by separating it with blank lines — a rich block body
        (paragraphs, lists, code) shown in the popover. Labeled asides in the
        same paragraph or list item collapse into one pill, with each aside kept
        as a separate popover page. Each unlabeled aside remains a separate
        numbered pill. The grouped pill shows a `+N` overflow count only when
        its labeled asides have different labels. Asides that share one label
        use a single face with no count.

        `grounded-span` identifies the answer text that is related to an aside.
        Its value must exactly match text before the tag in the same paragraph
        or list item. When the popover opens, shinychat highlights the most
        recent match. If the value does not match, no text is highlighted.

        Long content wraps and scrolls within the viewport. The popover keeps
        the nearest scoped Bootstrap theme. In a paged popover, page changes
        are announced to assistive technology without repeating the body.

        The favicon is fetched at render time from a third-party service
        (DuckDuckGo's icon service), which receives the cited site's hostname.
        To avoid that request — for privacy, or for offline/air-gapped
        deployments — set the ``SHINYCHAT_ASIDE_FAVICON`` environment variable
        to ``false``. You can still set `icon` to a URL you control; an
        explicit `icon` bypasses the lookup entirely.

        **Examples:**

        * A labeled aside with a grounded span and a one-line body:
          `Hub motors are cheaper<shiny-aside label="eBicycles" url="https://ebicycles.example/hub-vs-mid-drive" grounded-span="Hub motors are cheaper">[Hub Motor vs. Mid-Drive Motor Differences Explained](https://ebicycles.example/hub-vs-mid-drive)</shiny-aside>, and ideal for flatter terrain.`
        * Two asides cited in the same sentence collapse into a single pill
          — the first source's label becomes the face, with a "+1" overflow:
          `...<shiny-aside label="eBicycles" url="https://ebicycles.example">...</shiny-aside><shiny-aside label="WIRED" url="https://wired.example">...</shiny-aside>...`
        * A label-less aside with a rich block body (a blank line starts a
          block body instead of an inline one), falling back to a plain
          numbered pill:
          `Battery quality matters more than raw power<shiny-aside>\n\n**Methodology**\n\n- 40 commuter e-bike models\n- released in 2024\n\n</shiny-aside>`
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
        return await self._start_message_stream(message, icon=icon)

    async def _start_message_stream(
        self,
        message: Iterable[Any] | AsyncIterable[Any],
        *,
        icon: HTML | Tag | None = None,
        on_settled: Callable[[], Awaitable[None]] | None = None,
    ) -> ExtendedTask[[], str]:
        from shiny import reactive

        message = _utils.wrap_async_iterable(message)

        # Run the stream in the background to get non-blocking behavior
        @reactive.extended_task
        async def _stream_task() -> str:
            return await self._append_message_stream(message, icon=icon)

        _stream_task()

        self._latest_stream.set(_stream_task)

        settle_effect: Effect_ | None = None

        @reactive.effect
        async def _settle_stream():
            status = _stream_task.status()
            if status in ("initial", "running"):
                return

            response_error = _stream_task.error() if status == "error" else None
            try:
                await self._settle_response(
                    on_settled,
                    response_error=response_error,
                )
            finally:
                try:
                    if response_error is not None:
                        await self._raise_exception(response_error)
                finally:
                    assert settle_effect is not None
                    settle_effect.destroy()

        settle_effect = _settle_stream
        return _stream_task

    async def _settle_response(
        self,
        on_settled: Callable[[], Awaitable[None]] | None,
        *,
        response_error: BaseException | None,
    ) -> None:
        if on_settled is None:
            return
        try:
            await on_settled()
        except Exception as history_error:
            if response_error is None:
                await self.history._notify_save_error(history_error)
            else:
                warnings.warn(
                    f"Could not save conversation: {history_error}",
                    stacklevel=1,
                )

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
        icon: HTML | Tag | bool | None = None,
    ):
        id = _utils.private_random_id()

        empty = ChatMessageDict(content="", role="assistant")
        try:
            await self._append_message_chunk(
                empty, chunk="start", stream_id=id, icon=icon
            )
        except BaseException:
            await self._abort_message_stream(id)
            raise

        primary_error: BaseException | None = None

        iterator = message.__aiter__()
        while True:
            try:
                msg = await iterator.__anext__()
            except StopAsyncIteration:
                break
            except BaseException as error:
                primary_error = error
                break

            try:
                await self._append_message_chunk(msg, chunk=True, stream_id=id)
            except BaseException:
                await self._abort_message_stream(id)
                raise

        result = (
            ""
            if primary_error is not None
            else "".join(str(s) for s in self._transcript.active_segments)
        )

        try:
            await self._append_message_chunk(empty, chunk="end", stream_id=id)
        except BaseException as error:
            if primary_error is None:
                primary_error = error
            await self._abort_message_stream(id)

        if primary_error is not None:
            raise primary_error
        return result

    # Send a message to the UI
    async def _send_append_message(
        self,
        message: StoredMessage | ChatMessage,
        chunk: ChunkOption = False,
        operation: Literal["append", "replace"] = "append",
        icon: HTML | Tag | TagList | bool | None = None,
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
            message.segments[-1].content_type
            if message.segments
            else "markdown"
        )

        msg_payload: MessagePayload = {
            "role": message.role,
            "segments": message.wire_segments(),
        }
        if message.attachments:
            msg_payload["attachments"] = [
                a.model_dump() for a in message.attachments
            ]
        icon_attr = _resolve_icon_attr(icon)
        if icon_attr is not None:
            msg_payload["icon"] = icon_attr

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
        messages = self._transcript.read()

        dumps: list[dict[str, Any]] = []
        for m in messages:
            d = m.model_dump(exclude_none=True)
            if not d.get("attachments"):
                d.pop("attachments", None)
            dumps.append(d)
        return dumps

    async def _restore_bookmark_message(self, message_dict: Any) -> None:
        try:
            stored = StoredMessage.model_validate(message_dict)
        except ValidationError as e:
            raise ValueError(
                "Cannot restore bookmark message: invalid or missing fields "
                "(bookmark likely written by an incompatible shinychat version)."
            ) from e

        async def send() -> None:
            await self._send_append_message(stored)

        await self._transcript.append(stored, send=send)
        self._note_latest_user_input(stored)

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
            ChatMessage(
                content=content,
                role=res.role,
                attachments=message.attachments,
            ),
            html_deps=res.html_deps,
        )

    def _needs_transform(self, message: ChatMessage) -> bool:
        return (
            message.role == "assistant"
            and self._transform_assistant is not None
        )

    def _settled_stream_projection(
        self,
        projection: StoredMessage | None,
        segments: list[ContentSegment],
    ) -> StoredMessage | None:
        if projection is None:
            return None

        settled = projection.model_copy(deep=True)
        if settled.segments:
            settled.segments[0].html_deps = self._serialize_html_deps(
                segments_deps(segments)
            )
        return settled

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

    async def _store_message(
        self,
        message: StoredMessage | ChatMessage,
    ) -> None:
        stored = self._as_stored_message(message)

        async def noop() -> None:
            return None

        await self._transcript.append(stored, send=noop)
        self._note_latest_user_input(stored)

    def _note_latest_user_input(self, message: StoredMessage) -> None:
        if message.role == "user":
            self._latest_user_input.set(message)

    def user_input(self) -> "UserInput | None":
        """
        Reactively read the user's latest submission.

        Returns
        -------
        UserInput | None
            ``None`` before the first user submission; otherwise a named tuple
            of the submitted text and any attached files. The ``attachments``
            list is empty unless ``allow_attachments`` was enabled in
            :func:`~shinychat.chat_ui`. Supports destructuring after a
            ``None`` check::

                result = chat.user_input()
                if result is not None:
                    text, attachments = result

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
        return UserInput(text=str(msg.content), attachments=msg.attachments)

    def _user_input(self) -> "tuple[str, list[Attachment]]":
        val = cast("UserInputValue", self._session.input[self.user_input_id]())
        return val["text"], val["attachments"]

    def _slash_command_input(self) -> dict[str, Any]:
        return self._session.input[self._slash_command_id]()

    def update_user_input(
        self,
        *,
        value: str | None = None,
        placeholder: str | None = None,
        submit: bool = False,
        focus: bool = False,
        attachments: "list[Attachment] | None" = None,
        attachment_mode: "Literal['append', 'set']" = "append",
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
            Whether to automatically submit the text for the user. Requires ``value``.
        focus
            Whether to move focus to the input element. Requires ``value`` or
            ``attachments``.
        attachments
            Attachments to stage in the input. Pass an empty list to clear any
            currently staged attachments. When ``submit=True`` the attachments are
            sent alongside ``value`` and then cleared from the input.
        attachment_mode
            How to combine ``attachments`` with any already-staged attachments.
            ``"append"`` (default) adds to the existing set; ``"set"`` replaces it.
            Pass ``attachment_mode="set"`` with ``attachments=[]`` to clear all staged
            attachments.
        """

        if submit and value is None:
            raise ValueError(
                "An input `value` must be provided when `submit=True`."
            )
        if focus and value is None and not attachments:
            raise ValueError(
                "An input `value` or `attachments` must be provided when `focus=True`."
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
        if attachments is not None:
            action["attachments"] = [
                {
                    "mime": a.mime,
                    "data_url": a.data_url,
                    "name": a.name,
                    "size": a.size,
                }
                for a in attachments
            ]
            if attachment_mode != "append":
                action["attachment_mode"] = attachment_mode

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
        async with self._message_lock:
            action: ClearAction = {"type": "clear"}
            if greeting:
                self._greeting_snapshot = None
                action["greeting"] = True

            async def send() -> None:
                await self._send_action(action)

            await self._transcript.clear(send=send)

    def get_greeting(self) -> str | None:
        """
        Get the current greeting content.

        Returns
        -------
        str or None
            The current greeting content, or ``None`` if no greeting is set or
            has been cleared.
        """
        snapshot = self._greeting_snapshot
        return None if snapshot is None else snapshot["content"]

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
              ``persistent``.
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
        When the user dismisses the greeting, ``{id}_greeting_dismissed`` fires with
        a ``Date.now()`` timestamp. If the greeting is later cleared after being dismissed,
        the input resets to ``None``.

        Examples
        --------
        Static greeting (stand-alone, dismissed on first message by default):

        ```python
        @reactive.effect
        async def _():
            await chat.set_greeting(
                "## Welcome!\\n\\nHow can I help you today?"
            )
        ```

        Static greeting with custom options:

        ```python
        from shinychat import chat_greeting


        @reactive.effect
        async def _():
            greeting = chat_greeting(
                "## Welcome!",
                persistent=True,
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
            self._greeting_snapshot = None
            await self._send_action({"type": "greeting_clear"})
            return

        if not isinstance(greeting, ChatGreeting):
            greeting = chat_greeting(greeting)

        options: GreetingOptions = {"persistent": greeting.persistent}
        html_deps = (
            self._serialize_html_deps(greeting.html_deps)
            if greeting.html_deps
            else None
        )

        content = greeting.content
        if isinstance(content, AsyncIterable):
            start_action: ChatAction = {
                "type": "greeting_start",
                "content": "",
                "content_type": greeting.content_type,
                "options": options,
            }
            await self._send_action(start_action)
            chunks: list[str] = []
            try:
                async for chunk in content:
                    chunks.append(chunk)
                    chunk_action: ChatAction = {
                        "type": "greeting_chunk",
                        "content": chunk,
                        "operation": "append",
                    }
                    await self._send_action(chunk_action)
            finally:
                await self._send_action({"type": "greeting_end"})

            snapshot: GreetingSnapshot = {
                "content": "".join(chunks),
                "content_type": greeting.content_type,
                "options": options,
                "html_deps": html_deps or [],
            }
            self._greeting_snapshot = snapshot
        else:
            action: ChatAction = {
                "type": "greeting",
                "content": str(content),
                "content_type": greeting.content_type,
                "options": options,
            }
            snapshot: GreetingSnapshot = {
                "content": str(content),
                "content_type": greeting.content_type,
                "options": options,
                "html_deps": html_deps or [],
            }
            await self._send_action(action, snapshot["html_deps"])
            self._greeting_snapshot = snapshot

    async def _restore_greeting_snapshot(
        self,
        snapshot: GreetingSnapshot,
    ) -> None:
        action: GreetingAction = {
            "type": "greeting",
            "content": snapshot["content"],
            "content_type": snapshot["content_type"],
            "options": snapshot["options"],
        }
        await self._send_action(action, snapshot["html_deps"])
        self._greeting_snapshot = snapshot

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
        and `client=` instances, including the current greeting content. This means
        dynamic greetings survive bookmark round-trips without any extra app-level
        plumbing. In order for this method to actually work correctly, a
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
        for suffix in (
            "_user_input",
            "_cancel",
            "_slash_command",
            "_greeting_requested",
            "_greeting_dismissed",
        ):
            root_session.bookmark.exclude.append(self.id + suffix)

        # ###########
        # Bookmarking

        cancel_on_bookmarked: CancelCallback | None = None
        if bookmark_on is not None:
            # When ever the bookmark is requested, update the query string (indep of store type)
            async def _update_query_string_on_bookmarked(url: str) -> None:
                await session.bookmark.update_query_string(url)

            cancel_on_bookmarked = root_session.bookmark.on_bookmarked(
                _update_query_string_on_bookmarked
            )

        effect_auto_bookmark = None
        if bookmark_on == "response":

            @reactive.effect
            @reactive.event(self.messages, ignore_init=True)
            async def _auto_bookmark() -> None:
                messages = self.messages()

                if len(messages) == 0:
                    return

                last_message = messages[-1]

                if last_message.get("role") == "assistant":
                    await session.bookmark()

            effect_auto_bookmark = _auto_bookmark

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
                state.values[resolved_bookmark_id_msgs_str] = (
                    self._messages_for_bookmark()
                )

        resolved_greeting_key = resolved_bookmark_id_str + "--greeting"

        @root_session.bookmark.on_bookmark
        def _on_bookmark_greeting(state: BookmarkState):
            if self._greeting_snapshot is not None:
                state.values[resolved_greeting_key] = self._greeting_snapshot

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

            await self._transcript.replace(())
            for message_dict in msgs:
                await self._restore_bookmark_message(message_dict)

        @root_session.bookmark.on_restore
        async def _on_restore_greeting(state: RestoreState):
            if resolved_greeting_key not in state.values:
                return
            try:
                validated = GreetingSnapshotModel.model_validate(
                    state.values[resolved_greeting_key]
                )
            except ValidationError as e:
                raise ValueError(
                    "Cannot restore bookmark greeting: invalid or missing fields "
                    "(bookmark likely written by an incompatible shinychat version)."
                ) from e
            await self._restore_greeting_snapshot(validated.to_snapshot())

        def _cancel_bookmarking():
            if cancel_on_bookmarked is not None:
                cancel_on_bookmarked()
            if effect_auto_bookmark is not None:
                effect_auto_bookmark.destroy()
            _on_bookmark_client()
            _on_bookmark_ui()
            _on_bookmark_greeting()
            _on_restore_client()
            _on_restore_ui()
            _on_restore_greeting()

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
        icon_assistant: HTML | Tag | TagList | bool | None = None,
        enable_cancel: "bool | MISSING_TYPE" = MISSING,
        submit_key: 'Literal["enter", "enter+modifier"]' = "enter",
        allow_attachments: "bool | list[str] | MISSING_TYPE" = MISSING,
        footer: Optional[TagChild] = None,
        tool_grouping: 'Literal["none", "tool", "all"]' = "tool",
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
            the form of :class:`~htmltools.HTML` or :class:`~htmltools.Tag`. If `None`
            (or `True`), a default robot icon is used. Pass `False` to remove the
            assistant icon entirely (individual messages can still opt back in via
            the `icon` argument of `.append_message()`).
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
        allow_attachments
            Controls the file-attachment affordance (an attach button, plus clipboard
            paste and drag-and-drop) in the chat input. Pass ``True`` to accept all
            supported types (PNG, JPEG, GIF, WebP, PDF, and common text/code files
            such as Markdown, plain text, CSV, JSON, and source files), ``False`` to
            disable, or a list of MIME types to restrict what is accepted (each must
            be one of the supported types). Attachments are delivered to your
            ``.on_user_submit()`` handler's second argument as a
            ``list[Attachment]``, where each item exposes ``mime``, ``name``,
            ``size``, and ``data_url`` attributes (and forwarded to a ``client=``
            automatically). When left unset (the default), a chat driven by a
            ``client=`` enables attachments automatically; otherwise it stays
            hidden.

            The maximum combined size of all attachments in a single message is
            controlled globally by the ``SHINYCHAT_MAX_ATTACHMENT_SIZE`` environment
            variable (a raw byte count; defaults to approximately 30 MB). Files that
            would push the total over this cap are rejected in the browser with a notice.

            When bookmarking is enabled, prefer ``bookmark_store="server"``:
            attachment data is saved in the bookmark and can exceed URL length
            limits with ``bookmark_store="url"``.
        footer
            Optional HTML content to display below the chat input.
            This can be any HTML content (tags, tag lists, or strings).
            Useful for adding disclaimers, attribution, or other information.
            The footer text is styled slightly smaller and lighter than body text
            by default. Customize with CSS properties ``--shiny-chat-footer-font-size``
            and ``--shiny-chat-footer-color`` on the chat container or footer element.
        tool_grouping
            Controls how tool calls are grouped together in the UI:

            - ``"tool"`` (default): calls to the *same* tool within a
              tool-calling loop are grouped into a single activity row.
              This groups by tool name across the whole loop, not just
              consecutive calls -- e.g. calls to tools ``X``, ``Y``, ``Z``,
              ``X``, ``Y`` (in that order) are grouped into ``X`` (2 calls),
              ``Y`` (2 calls), and ``Z`` (1 call).
            - ``"all"``: every tool call within a tool-calling loop is
              grouped into a single activity row, regardless of tool name.
            - ``"none"``: each tool call is shown in its own activity row.

            Prose or thinking between calls starts a new tool-calling loop, so
            grouping never crosses those transcript boundaries.

            Individual tools can override this via a ``grouping`` tool
            annotation. For chatlas tools, prefer
            ``annotations={"extra": {"grouping": ...}}``: a top-level
            ``grouping`` key is also read, but it isn't part of chatlas'
            ``ToolAnnotations``, so type checkers reject it. Chat-level
            ``"none"`` always disables grouping, even when a tool annotation
            requests ``"tool"`` or ``"all"``.
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
            allow_attachments=allow_attachments,
            footer=footer,
            tool_grouping=tool_grouping,
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


def _resolve_icon_attr(
    icon: "HTML | Tag | TagList | bool | None",
) -> "str | None":
    """Translate an icon value into its wire attribute.

    ``False`` removes the icon (wire ``""``, which the client reads as "no
    icon"); ``True``/``None`` defer to the default (attribute omitted);
    anything else is stringified HTML.
    """
    if icon is None or icon is True:
        return None
    if icon is False:
        return ""
    return str(icon)


def _container_style(width: "str | None", height: "str | None") -> "str | None":
    # `width` is emitted as a pseudo-private custom property consumed by
    # `.shiny-chat-wrapper` (as max-width), so the container itself stays
    # full-width and the drawer scrim can span it. Built by hand because
    # htmltools `css()` mangles the leading `--` of a custom property.
    parts: list[str] = []
    if width:
        parts.append(f"--_chat-width:{width}")
    if height:
        parts.append(f"height:{height}")
    return ";".join(parts) if parts else None


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
    icon_assistant: Optional[HTML | Tag | TagList | bool] = None,
    enable_cancel: "bool | MISSING_TYPE" = MISSING,
    submit_key: 'Literal["enter", "enter+modifier"]' = "enter",
    allow_attachments: "bool | list[str] | MISSING_TYPE" = MISSING,
    footer: Optional[TagChild] = None,
    tool_grouping: 'Literal["none", "tool", "all"]' = "tool",
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
            the form of :class:`~htmltools.HTML` or :class:`~htmltools.Tag`. If `None`
            (or `True`), a default robot icon is used. Pass `False` to remove the
            assistant icon entirely (individual messages can still opt back in via
            the `icon` argument of `.append_message()`).
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
    allow_attachments
        Controls the file-attachment affordance (an attach button, plus clipboard
        paste and drag-and-drop) in the chat input. Pass ``True`` to accept all
        supported types (PNG, JPEG, GIF, WebP, PDF, and common text/code files
        such as Markdown, plain text, CSV, JSON, and source files), ``False`` to
        disable, or a list of MIME types to restrict what is accepted (each must
        be one of the supported types). Attachments are delivered to your
        ``.on_user_submit()`` handler's second argument as a
        ``list[Attachment]``, where each item exposes ``mime``, ``name``,
        ``size``, and ``data_url`` attributes (and forwarded to a ``client=``
        automatically). When left unset (the default), a chat driven by a
        ``client=`` enables attachments automatically; otherwise it stays
        hidden.

        The maximum combined size of all attachments in a single message is
        controlled globally by the ``SHINYCHAT_MAX_ATTACHMENT_SIZE`` environment
        variable (a raw byte count; defaults to approximately 30 MB). Files that
        would push the total over this cap are rejected in the browser with a notice.

        When bookmarking is enabled, prefer ``bookmark_store="server"``:
        attachment data is saved in the bookmark and can exceed URL length
        limits with ``bookmark_store="url"``.
    footer
        Optional HTML content to display below the chat input.
        This can be any HTML content (tags, tag lists, or strings).
        Useful for adding disclaimers, attribution, or other information.
        The footer text is styled slightly smaller and lighter than body text
        by default. Customize with CSS properties ``--shiny-chat-footer-font-size``
        and ``--shiny-chat-footer-color`` on the chat container or footer element.
    tool_grouping
        Controls how tool calls are grouped together in the UI:

        - ``"tool"`` (default): calls to the *same* tool within a tool-calling
          loop are grouped into a single activity row.
          This groups by tool name across the whole loop, not just
          consecutive calls -- e.g. calls to tools ``X``, ``Y``, ``Z``, ``X``,
          ``Y`` (in that order) are grouped into ``X`` (2 calls), ``Y``
          (2 calls), and ``Z`` (1 call).
        - ``"all"``: every tool call within a tool-calling loop is
          grouped into a single activity row, regardless of tool name.
        - ``"none"``: each tool call is shown in its own activity row.

        Prose or thinking between calls starts a new tool-calling loop, so
        grouping never crosses those transcript boundaries.

        Individual tools can override this via a ``grouping`` tool annotation.
        For chatlas tools, prefer ``annotations={"extra": {"grouping": ...}}``:
        a top-level ``grouping`` key is also read, but it isn't part of
        chatlas' ``ToolAnnotations``, so type checkers reject it. Chat-level
        ``"none"`` always disables grouping, even when a tool annotation
        requests ``"tool"`` or ``"all"``.
    kwargs
        Additional attributes for the chat container element.
    """
    from shiny.module import resolve_id
    from shiny.ui.css import as_css_unit
    from shiny.ui.fill import as_fill_item, as_fillable_container

    id = resolve_id(id)

    # The client silently falls back to "tool" for an unrecognized value, so
    # catch typos here instead of shipping the wrong grouping mode. (Also
    # covers `ChatExpress.ui()`, which delegates here.)
    if tool_grouping not in ("none", "tool", "all"):
        raise ValueError(
            '`tool_grouping` must be one of "none", "tool", or "all", '
            f"not {tool_grouping!r}."
        )

    icon_attr = _resolve_icon_attr(icon_assistant)

    icon_deps = None
    if isinstance(icon_assistant, (Tag, TagList)):
        icon_deps = icon_assistant.get_dependencies()

    message_tags: list[Tag] = []
    if messages is None:
        messages = []
    for x in messages:
        msg = normalize_message(x)
        message_tags.append(
            Tag(
                "shiny-chat-message",
                *msg.html_deps,
                content=msg.content,
                # The assistant default must not leak onto user messages, which
                # render `message.icon` directly (no assistant fallback chain).
                icon=icon_attr if msg.role != "user" else None,
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

    # allow_attachments resolves to two attributes: the tri-state
    # `allow-attachments` gate (omitted defers to `client=` via `update_upload`)
    # and an optional `attachment-accept` CSV restricting accepted MIME types.
    allow_attachments_attr, attachment_accept_attr = resolve_attachment_attrs(
        allow_attachments
    )
    max_attachment_size_attr = str(resolve_max_attachment_size())
    aside_favicon_attr = None if resolve_aside_favicon() else "false"

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
            "options": {"persistent": greeting.persistent},
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
        {"style": _container_style(as_css_unit(width), as_css_unit(height))},
        id=id,
        placeholder=placeholder,
        fill=fill,
        greeting=greeting_attr,
        aside_favicon=aside_favicon_attr,
        enable_cancel=enable_cancel_attr,
        allow_attachments=allow_attachments_attr,
        attachment_accept=attachment_accept_attr,
        max_attachment_size=max_attachment_size_attr,
        # Also include icon on the parent so that when messages are dynamically added,
        # we know the default icon has changed
        icon_assistant=icon_attr,
        submit_key=submit_key if submit_key != "enter" else None,
        tool_grouping=tool_grouping if tool_grouping != "tool" else None,
        **kwargs,
    )

    if fill:
        res = as_fillable_container(as_fill_item(res))

    return res


ASIDE_FAVICON_ENV_VAR = "SHINYCHAT_ASIDE_FAVICON"


def resolve_aside_favicon() -> bool:
    value = os.environ.get(ASIDE_FAVICON_ENV_VAR, "true").lower()
    if value == "true":
        return True
    if value == "false":
        return False
    raise ValueError(
        f'{ASIDE_FAVICON_ENV_VAR} must be "true" or "false", got {value!r}.'
    )


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


CHAT_INSTANCES: WeakValueDictionary[str, Chat] = WeakValueDictionary()
