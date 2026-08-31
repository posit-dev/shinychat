import json
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any, AsyncIterable, Iterable, Literal, Union

from htmltools import Tag, TagChild, css

from ._chat_types import HtmlBlock, StructuredBlock, serialize_html_deps
from ._html_deps_py_shiny import shinychat_dependency
from ._html_islands import (
    IslandBlockPart,
    derive_island_parts,
    split_content_by_trust,
)
from ._typing_extensions import NotRequired, TypedDict

if TYPE_CHECKING:
    from shiny import reactive
    from shiny.ui.css import CssUnit

__all__ = (
    "output_markdown_stream",
    "MarkdownStream",
    "ExpressMarkdownStream",
)

StreamingContentType = Literal[
    "markdown",
    "html",
    "text",
]


class ContentMessage(TypedDict):
    id: str
    operation: Literal["append", "replace"]
    html_deps: list[dict[str, Any]]
    trusted: bool
    segment_start: bool
    # A message carries `content` XOR `block` (kata#mhyd). Blocks arrive
    # complete and append-only; `html_block` envelopes are derived from
    # trusted UI, and `stream()` also accepts already-structured block
    # dicts (e.g. web_search) which pass through as-is.
    content: NotRequired[str]
    block: NotRequired[StructuredBlock]


class isStreamingMessage(TypedDict):
    id: str
    isStreaming: bool


class MarkdownStream:
    """
    A component for streaming markdown or HTML content.

    Parameters
    ----------
    id
        A unique identifier for this `MarkdownStream`. In Shiny Core, make sure this id
        matches a corresponding :func:`~shiny.ui.output_markdown_stream` call in the app's
        UI.
    on_error
        How to handle errors that occur while streaming. When `"unhandled"`,
        the app will stop running when an error occurs. Otherwise, a notification
        is displayed to the user and the app continues to run.

        * `"auto"`: Sanitize the error message if the app is set to sanitize errors,
          otherwise display the actual error message.
        * `"actual"`: Display the actual error message to the user.
        * `"sanitize"`: Sanitize the error message before displaying it to the user.
        * `"unhandled"`: Do not display any error message to the user.

    Note
    ----
    Markdown is parsed on the client via `marked.js`. Consider using
    :func:`~shiny.ui.markdown` for server-side rendering of markdown content.
    """

    def __init__(
        self,
        id: str,
        *,
        on_error: Literal["auto", "actual", "sanitize", "unhandled"] = "auto",
    ):
        from shiny.module import resolve_id
        from shiny.session import require_active_session

        self.id = resolve_id(id)
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

        from shiny import reactive
        from shiny.session import session_context

        with session_context(self._session):

            @reactive.extended_task
            async def _mock_task() -> str:
                return ""

            self._latest_stream: "reactive.Value[reactive.ExtendedTask[[], str]]" = reactive.Value(
                _mock_task
            )

    async def stream(
        self,
        content: Union[
            Iterable[Union[TagChild, StructuredBlock]],
            AsyncIterable[Union[TagChild, StructuredBlock]],
        ],
        clear: bool = True,
    ):
        """
        Send a stream of content to the UI.

        Stream content into the relevant UI element.

        Parameters
        ----------
        content
            The content to stream. This can be a Iterable or an AsyncIterable of strings.
            Note that this includes synchronous and asynchronous generators, which is
            a useful way to stream content in as it arrives (e.g. from a LLM).

            An item may also be an already-structured content block dict (e.g. a
            `web_search`/`web_search_results`/`web_fetch` block of the kind
            chatlas normalization produces for `Chat`). Each block dict is sent
            as one complete, append-only structured block message (kata#mhyd);
            the client validates, groups, and renders it.
        clear
            Whether to clear the existing content before streaming the new content.

        Note
        ----
        If you already have the content available as a string, you can do
        `.stream([content])` to set the content.

        Returns
        -------
        :
            An extended task that represents the streaming task. The `.result()` method
            of the task can be called in a reactive context to get the final state of the
            stream.
        """
        from shiny import _utils, reactive

        content = _utils.wrap_async_iterable(content)

        @reactive.extended_task
        async def _task():
            if clear:
                await self._send_content_message(
                    "",
                    "replace",
                    [],
                    trusted=False,
                    segment_start=True,
                )

            result = ""
            async with self._streaming_dot():
                async for x in content:
                    if isinstance(x, dict):
                        # An already-structured block (e.g. web_search) ships
                        # as one complete block message (content XOR block,
                        # kata#mhyd). The client validates it (dropping
                        # invalid/unsupported types with a warning) and
                        # groups web_* blocks into the trailing web activity.
                        # Blocks contribute nothing to the text result
                        # (mirroring Chat's empty-content snapshot of a
                        # web_activity block).
                        await self._send_block_message(x, [])
                        continue
                    segments = split_content_by_trust(x)
                    composite = not isinstance(x, str) or len(segments) > 1
                    for index, (trusted, segment) in enumerate(segments):
                        if trusted:
                            # Trusted (server-authored) content walks the
                            # shared island derivation (kata#mhyd): island
                            # wrappers ship as structured html_block
                            # block-messages; bare data-shinychat-react
                            # elements stay trusted residual string segments.
                            parts = list(derive_island_parts(segment))
                            # Aggregate the whole run's deps onto the FIRST
                            # outbound envelope (block or string): the client
                            # renders envelope deps before dispatching the
                            # message, so every dependency of the run loads
                            # before any of its parts mount — the invariant
                            # the pre-block whole-fragment emission had. Later
                            # parts send empty envelope deps; a block still
                            # carries its own deps for its mount gate
                            # (mirroring ChatMessage's message-level +
                            # block-level split).
                            run_deps = (
                                serialize_html_deps(
                                    [
                                        dep
                                        for part in parts
                                        for dep in part.deps
                                    ],
                                    self._session,
                                )
                                or []
                            )
                            for part_index, part in enumerate(parts):
                                envelope_deps = (
                                    run_deps if part_index == 0 else []
                                )
                                if isinstance(part, IslandBlockPart):
                                    block: HtmlBlock = {
                                        "type": "html_block",
                                        "version": 1,
                                        "content": part.html,
                                    }
                                    block_deps = serialize_html_deps(
                                        part.deps, self._session
                                    )
                                    if block_deps:
                                        block["html_deps"] = block_deps
                                    result += part.html
                                    await self._send_block_message(
                                        block, envelope_deps
                                    )
                                else:
                                    result += part.html
                                    await self._send_content_message(
                                        part.html,
                                        "append",
                                        envelope_deps,
                                        trusted=True,
                                        segment_start=True,
                                    )
                        else:
                            text = str(segment)
                            result += text
                            await self._send_content_message(
                                text,
                                "append",
                                [],
                                trusted=False,
                                segment_start=composite or index > 0,
                            )

            return result

        _task()

        self._latest_stream.set(_task)

        # Since the task runs in the background (outside/beyond the current context,
        # if any), we need to manually raise any exceptions that occur
        @reactive.effect
        async def _handle_error():
            e = _task.error()
            if e:
                await self._raise_exception(e)
            _handle_error.destroy()  # type: ignore

        return _task

    @property
    def latest_stream(self):
        """
        React to changes in the latest stream.

        Reactively reads for the :class:`~shiny.reactive.ExtendedTask` behind the
        latest stream.

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

    def get_latest_stream_result(self) -> Union[str, None]:
        """
        Reactively read the latest stream result.

        Deprecated. Use `latest_stream.result()` instead.
        """
        from shiny._deprecated import warn_deprecated

        warn_deprecated(
            "The `.get_latest_stream_result()` method is deprecated and will be removed "
            "in a future release. Use `.latest_stream.result()` instead. "
        )
        return self.latest_stream.result()

    async def clear(self):
        """
        Empty the UI element of the `MarkdownStream`.
        """
        return await self.stream([], clear=True)

    @asynccontextmanager
    async def _streaming_dot(self):
        await self._send_stream_message(True)
        try:
            yield
        finally:
            await self._send_stream_message(False)

    async def _send_content_message(
        self,
        content: str,
        operation: Literal["append", "replace"],
        html_deps: list[dict[str, Any]],
        *,
        trusted: bool,
        segment_start: bool,
    ):
        msg: ContentMessage = {
            "id": self.id,
            "content": content,
            "operation": operation,
            "html_deps": html_deps,
            "trusted": trusted,
            "segment_start": segment_start,
        }
        await self._send_custom_message(msg)

    async def _send_block_message(
        self, block: StructuredBlock, html_deps: list[dict[str, Any]]
    ):
        """Send one complete structured block (content XOR block, kata#mhyd).

        The block's own `html_deps` carry its dependencies (serialized
        through `session._process_ui` by the caller) for its mount gate —
        mirroring Chat's `block_insert` actions. The envelope's `html_deps`
        carry the aggregated deps of the block's whole trusted run (empty
        for later parts of the run), which the client renders before
        dispatching the message, so all deps of a run load before any of
        its parts mount.
        """
        msg: ContentMessage = {
            "id": self.id,
            "operation": "append",
            "html_deps": html_deps,
            "trusted": True,
            "segment_start": True,
            "block": block,
        }
        await self._send_custom_message(msg)

    async def _send_stream_message(self, is_streaming: bool):
        msg: isStreamingMessage = {
            "id": self.id,
            "isStreaming": is_streaming,
        }
        await self._send_custom_message(msg)

    async def _send_custom_message(
        self, msg: Union[ContentMessage, isStreamingMessage]
    ):
        if self._session.is_stub_session():
            return
        await self._session.send_custom_message(
            "shinyMarkdownStreamMessage", {**msg}
        )

    async def _raise_exception(self, e: BaseException):
        from shiny.types import NotifyException

        if self.on_error == "unhandled":
            raise e
        else:
            sanitize = self.on_error == "sanitize"
            msg = f"Error in MarkdownStream('{self.id}'): {str(e)}"
            raise NotifyException(msg, sanitize=sanitize) from e


class ExpressMarkdownStream(MarkdownStream):
    def ui(
        self,
        *,
        content: TagChild = "",
        content_type: StreamingContentType = "markdown",
        auto_scroll: bool = True,
        width: "CssUnit" = "min(680px, 100%)",
        height: "CssUnit" = "auto",
    ) -> Tag:
        """
        Create a UI element for this `MarkdownStream`.

        Parameters
        ----------
        content
            A string of content to display before any streaming occurs. When
            `content_type` is Markdown or HTML, it may also be UI element(s) such as
            input and output bindings.
        content_type
            The content type. Default is `"markdown"` (specifically, CommonMark).
            Supported content types include:
                - `"markdown"`: markdown text, specifically CommonMark
                - `"html"`: for rendering HTML content.
                - `"text"`: for plain text.
        auto_scroll
            Whether to automatically scroll to the bottom of a scrollable container
            when new content is added. Default is `True`.
        width
            The width of the UI element.
        height
            The height of the UI element.

        Returns
        -------
        Tag
            A UI element for locating the `MarkdownStream` in the app.
        """
        return output_markdown_stream(
            self.id,
            content=content,
            content_type=content_type,
            auto_scroll=auto_scroll,
            width=width,
            height=height,
        )


def output_markdown_stream(
    id: str,
    *,
    content: TagChild = "",
    content_type: StreamingContentType = "markdown",
    auto_scroll: bool = True,
    width: "CssUnit" = "min(680px, 100%)",
    height: "CssUnit" = "auto",
) -> Tag:
    """
    Create a UI element for a :class:`~shiny.ui.MarkdownStream`.

    This function is only relevant for Shiny Core. In Shiny Express, use
    :meth:`~shiny.express.ui.MarkdownStream.ui` to create the UI element.

    Parameters
    ----------
    id
        A unique identifier for the UI element. This id should match the id of the
        :class:`~shiny.ui.MarkdownStream` instance.
    content
        A string of content to display before any streaming occurs. When `content_type`
        is Markdown or HTML, it may also be UI element(s) such as input and output
        bindings.
    content_type
        The content type. Default is "markdown" (specifically, CommonMark). Supported
        content types include:
            - `"markdown"`: markdown text, specifically CommonMark
            - `"html"`: for rendering HTML content.
            - `"text"`: for plain text.
    auto_scroll
        Whether to automatically scroll to the bottom of a scrollable container
        when new content is added. Default is True.
    width
        The width of the UI element.
    height
        The height of the UI element.
    """
    from shiny.module import resolve_id
    from shiny.ui.css import as_css_unit

    rendered_segments: list[dict[str, Any]] = []
    dependencies = []
    for trusted, segment in split_content_by_trust(content):
        if trusted:
            # Trusted UI walks the shared island derivation (kata#mhyd):
            # island wrappers become {block: html_block} entries; bare
            # data-shinychat-react elements stay trusted residual text
            # segments. There is no session at UI-construction time, so
            # block deps carry the raw as_dict() serialization (the same
            # no-session fallback ChatMessage uses, kata#rpx1) and the dep
            # objects also propagate as page-level dependencies below.
            for part in derive_island_parts(segment):
                if isinstance(part, IslandBlockPart):
                    block: HtmlBlock = {
                        "type": "html_block",
                        "version": 1,
                        "content": part.html,
                    }
                    if part.deps:
                        block["html_deps"] = [d.as_dict() for d in part.deps]
                    rendered_segments.append({"block": block})
                else:
                    rendered_segments.append(
                        {"text": part.html, "trusted": True}
                    )
                dependencies.extend(part.deps)
        else:
            rendered_segments.append({"text": str(segment), "trusted": False})

    # The fallback `content` attribute carries every segment's HTML —
    # including island payloads — so a client that fails closed on the
    # provenance array (or predates block entries) still shows the content,
    # escaped and untrusted.
    rendered_content = "".join(
        str(seg["text"]) if "text" in seg else str(seg["block"]["content"])
        for seg in rendered_segments
    )
    # A block entry is never a trusted fallback: content-trusted only
    # governs the no-provenance path, and the fail-closed path must not
    # render fallback content as trusted.
    fallback_trusted = (
        len(rendered_segments) == 1
        and rendered_segments[0].get("trusted") is True
    )

    return Tag(
        "shiny-markdown-stream",
        shinychat_dependency(),
        dependencies,
        {
            "style": css(
                width=as_css_unit(width),
                height=as_css_unit(height),
                margin="0 auto",
            ),
            "content-type": content_type,
            "content-segments": json.dumps(
                rendered_segments, separators=(",", ":")
            ),
            "content-trusted": "true" if fallback_trusted else "false",
            "auto-scroll": "" if auto_scroll else None,
        },
        id=resolve_id(id),
        content=rendered_content,
    )
