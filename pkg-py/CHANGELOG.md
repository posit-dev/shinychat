# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [UNRELEASED]

### New features

* Conversations now have a stable, publicly accessible ID, available reactively via `chat.history.conversation_id()` (`None` when history is disabled or the chat is still empty). The ID is stable across retries, restores, conversation switches, and `chat.client.set()` calls, and becomes the saved `ConversationRecord.id`. The ID is also handed to the chat client, which records it as the standard `gen_ai.conversation.id` attribute on its own OpenTelemetry spans ([OTel GenAI semantic conventions](https://opentelemetry.io/docs/specs/semconv/registry/attributes/gen-ai/)), so telemetry consumers can group model work by conversation. (#307)

* Chatlas web search and web fetch responses now show their activity and citations directly in the chat. Readers can open a citation beside its claim or use the message-wide Sources pill. `ContentCitation.grounded_span` links each citation to the answer text that it supports.

* Assistant messages can now attach source details to specific claims with the `<shiny-aside>` markup convention. This convention powers shinychat's web citations and can also support custom RAG workflows. Add an inline `<shiny-aside>` tag with source details and an optional `grounded-span`. Shinychat shows a compact source pill and highlights the related text when the pill is open. See the `Asides` callout in the `append_message` and `append_message_stream` documentation.

* You can now edit a message you already sent, instead of only being able to send a new one. Hover a user message (or press and hold on a touch device) and click the pencil icon to open an inline editor (pre-filled with the original text and attachments); press Enter (or Cmd/Ctrl+Enter, depending on `submit_key`) to save and resend, or Escape to cancel. Editing forks the conversation from that point — the original branch isn't lost, it's kept as a sibling. `‹ 1 / 2 ›`-style controls appear on any message with more than one version, letting you step back and forth between them at any time, including after reloading the page or returning from the history drawer. Requires history to be enabled (the default when using `client=`). (#269)

* Tool calls now render as a condensed activity row by default. Expand a group row to see each individual call, then drill into a call to see its full request/result card. `ToolResultDisplay` gained `label` (a short per-call identifying value, e.g. a filename or query) and `value_preview` (a terse peek at the result, e.g. "1,204 rows"), both shown in the activity row and expanded call list.

* Added `tool_grouping` to `chat_ui()` / `Chat.ui()`: `"tool"` (default) groups calls to the same tool within a tool-calling loop (order-independent, not just consecutive calls); `"all"` groups every call in the loop together; `"none"` shows one activity row per call. Prose and thinking start a new loop. Individual tools can override `"tool"` or `"all"` via a `grouping` tool annotation -- for chatlas tools, set it under `annotations={"extra": {"grouping": ...}}`. Chat-level `"none"` always disables grouping.

* Fully custom `ContentToolResult` UI returned through a `message_content()` or `message_content_chunk()` handler now settles its pending tool activity row and renders as standalone output. This preserves the custom UI for streamed messages, static preloads, and restored conversations without requiring changes to existing handlers.

* `page_chat()` now supports standard Shiny programmatic navigation. The page shell's root element carries the derived ID `"<id>_page"`, so `shiny.ui.update_navset()` works against it. The active page is readable server-side as `input["<id>_page"]()` (`"__home__"` when the chat home is active).

### Changes

* `chat_ui()` and `Chat.ui()` now use a wider default content width on large
  displays while preserving their existing width on smaller windows. (#364)

* `chat_ui()` / `Chat.ui()` and `page_chat()` no longer show an assistant icon by default. Pass `icon_assistant=True` to restore the built-in robot icon, or supply your own icon as before. (#345)

* The CSS classes used by the external-link dialog, thinking display, and tool-result images/PDFs now use the `.shiny-chat-*` prefix instead of `.shinychat-*`. The thinking display's custom properties and animation names have likewise changed from `--shinychat-thinking-*` / `shinychat-thinking-*` to `--shiny-chat-thinking-*` / `shiny-chat-thinking-*`. Update any custom CSS that targets these identifiers. (#285, #286)

* The record of displayed messages is now sourced from the browser rather than a server-side accumulator. As a consequence, `chat.messages()` is *eventually* consistent: it returns an empty tuple until the client's first report, and a message passed to `chat.append_message()` does not appear there until the browser has rendered it and reported back. Read it reactively rather than expecting a synchronous update immediately after appending. (#272)

    * The user-submission input (`input[f"{id}_user_input"]`) is now a persistent regular input rather than an event-priority one, so it retains its last value between submissions. This lets it co-batch with the message snapshot in a single reactive flush. It remains excluded from bookmarks. (#272)

* A tool's definition `title` (from its annotations) and its result `title` (from `ToolResultDisplay`) are now shown as-is, without any client-side tense conjugation. The definition title is shown while the call is running and labels multi-call groups. For a single-call row, the result title (if provided) replaces it when the result arrives; in a multi-call group, a distinct result title can identify that call in the expanded list. The old `"Running {title}"` / `"{title} failed"` client-side title template has been removed. If a tool's title reads oddly while running now that the automatic "Running " prefix is gone, write an explicit present-tense definition title (e.g. "Running R code") and, optionally, a past-tense result title (e.g. "Ran R code"). Failures are shown via a separate status cue (a "failed"/"N failed" note and icon) rather than appended to the title.

* The `messages` parameter is deprecated in favor of the conversation-history feature. `Chat(messages=...)` now errors when history is enabled (the default); use `greeting` for a startup message, `Chat.append_message()` to replay messages, or `history=False` if you manage state yourself.

### Bug fixes

* Attachment data URLs must now use the declared MIME type and a valid base64 header. PDF previews are also restricted to PDF content and rendered in a sandboxed iframe, preventing mismatched attachment data from being interpreted as active HTML. (#325)

* Fixed `MarkdownStream` permanently stopping following new content after the user scrolled back to the bottom. Pinning was decided only from `scroll` events, which browsers dispatch asynchronously; if a chunk grew the container first, the user's at-bottom position no longer read as at-bottom and auto-scroll silently disengaged for good. (#282)

* Single tildes no longer trigger strikethrough in markdown. Text like `(~$1.50)` and `~/Documents` now renders as literal text; only `~~text~~` produces strikethrough. (#349, #353)

## [0.6.1] - 2026-08-14

### Bug fixes

* Conversation history now rejects records written with unsupported future schema versions instead of attempting an unsafe downgrade.

* Fixed a race between the chat greeting and conversation history restore: reloading a page that restored a previous conversation could briefly flash the app's greeting, and starting a new chat after a session began with a restored conversation could fail to show any greeting at all. Greeting resolution now defers to history's own restore decision instead of racing the client's independent greeting request.

* Restoring a bookmark that contains a malformed message (for instance one written by an incompatible shinychat version) now warns and skips just that message, instead of raising and dropping every message after it.

* Fixed conversation history and bookmarks failing to serialize a chatlas `ContentToolResult` when its supported dictionary-form `extra["display"]` contains HTML. Dictionary displays are now normalized through `ToolResultDisplay` before JSON serialization. (Related to #295)

## [0.6.0] - 2026-07-06

### New features

* `Chat(client=...)` now gets multi-conversation history automatically: a drawer for starting new chats and returning to previous ones, with LLM-generated titles, search, rename, and delete. Conversations are persisted per-user (or a custom scope) via a pluggable store — the default `FileConversationStore` finds a redeploy-safe location automatically on Posit Connect. Customize with `Chat(history=HistoryOptions(...))`, or opt out entirely with `history=False`. For apps that don't use `client=`, wire it up manually with `chat.history.enable()`. (#266)
    * `HistoryOptions(restore_mode=...)` controls how the active conversation is remembered across page reloads: `"browser"` (default) via `localStorage`, `"url"` via a `?shinychat_conversation_id=` query parameter, `"bookmark"` via full Shiny server bookmarking (requires `bookmark_store="server"`, and also restores raw input controls), or `"none"` to disable. Use `@chat.history.on_save` / `@chat.history.on_restore` to keep other app state (tabs, filters, model choice) synced to the active conversation. (#266)

* File attachment support: users can upload images, PDFs, and text files alongside chat messages via a file picker button, drag-and-drop, or clipboard paste. Enable with `chat_ui(allow_attachments=True)` or pass a list of MIME types to restrict accepted file types. When using `client=`, attachments are enabled automatically and converted to the appropriate chatlas content types. For manual wiring, declare a second `list[Attachment]` parameter on your `@chat.on_user_submit` handler and use `attachment_to_content()` to convert each attachment. The maximum combined attachment size defaults to approximately 30 MB and can be configured via the `SHINYCHAT_MAX_ATTACHMENT_SIZE` environment variable.

### Changes

* The `dismissible` parameter of `chat_greeting()` has been renamed to `persistent` with an inverted value. `dismissible=False` (greeting stays visible) is now `persistent=True`. The old `dismissible` argument still works but warns. (#260)

### Bug fixes

* Fixed suggestion cards and the greeting overflowing the chat container in narrow spaces such as sidebars. (#255)

## [0.5.1] - 2026-06-15

### Bug fixes

* `pydantic` is now a hard dependency. (#252)


## [0.5.0] - 2026-06-15

### New features

* `Chat()` now accepts an optional `client=` parameter. When provided, streaming, cancellation, bookmarking, and greeting handling are wired up automatically — no manual plumbing required. The `chat.client` property exposes a `ChatClient` wrapper with `.value` (the raw chatlas client), `.set()` for swapping models mid-session, and `.clear()` for resetting the conversation with flexible history management.

* Added slash commands: a typeahead command palette that lets users trigger named shortcuts directly from the chat input. Type `/` to open the palette, filter by typing, and pick a command with arrow keys or click. Commands can expand into LLM prompts, trigger server-side side effects (clear chat, open a modal, export transcript), or be handled entirely client-side via the cancelable `shiny:chat-slash-command` DOM event. Register commands with `chat.slash_command()`, which accepts 0- or 1-argument async handlers; 1-argument handlers receive the text typed after the command name as `user_input`. The `echo` parameter controls whether an invocation is recorded as a user message and triggers a loading state. Echoed commands are faithfully restored on bookmark/restore. (#239)

* Added `submit_key` parameter to `chat_ui()` and `Chat.ui()`: `"enter"` (default, Enter submits) or `"enter+modifier"` (Ctrl/Cmd+Enter submits, plain Enter inserts a line break). The input remains editable while a response is streaming — only submission is blocked, not typing. (#251)

### Improvements

* Bookmarking now correctly restores assistant messages that mix content types within a single message — for example a reply that combines markdown, a raw-HTML widget, and reasoning. Previously, restoring such a message could lose formatting or interactive components.

* All navigating links in assistant messages now open in a new tab to preserve the app's session state. Cross-origin links still show the confirmation dialog; same-origin links open directly. (#238)

### Breaking changes

* `Chat.user_input()` now returns a `UserInput` named tuple (`text`, `attachments`) instead of just the submitted text string. Existing code that treats `chat.user_input()` as a string should be updated to read `result.text` (or destructure `text, attachments`) after the `None` check.

* Removed the deprecated `format` and `token_limits` parameters from `.messages()`, the `tokenizer` parameter from `Chat()`, and the `.transform_user_input()` decorator. These features overreached into LLM provider responsibilities; use your provider (e.g., chatlas, LangChain) to manage conversation formatting, token limits, and input transformation instead. Calling any of these now raises a `TypeError` with migration guidance. (#245)

### Bug fixes

* Fixed the copy button on code blocks not working in some embedded contexts. (@thisisnic, #247)

* Fixed the external link confirmation dialog not rendering in Safari. The backdrop overlay appeared but the dialog content was invisible due to a Bootstrap/`<dialog>` CSS interaction. (#201, #238)

* Fixed pressing Escape to dismiss the external link dialog leaving it in a broken state where subsequent link clicks no longer worked. (#238)

* Fixed a bug where `<thinking>` tags inside fenced code blocks (` ``` `) or inline backtick spans were incorrectly treated as model reasoning content and hidden from the visible output. Also fixes a chunk-boundary false positive where a chunk ending with a non-newline character followed by a chunk beginning with `<thinking>` would enter thinking mode. (#235)

## [0.4.0] - 2026-05-26

### New features

* The chat UI now displays model reasoning/thinking content as collapsible panels above assistant responses. Thinking content streams in real-time with animated topic labels. This works with providers that support structured thinking (e.g., Claude's extended thinking via `chatlas`) and with local models that wrap reasoning in `<thinking>` tags. (#208)

* Added `chat_greeting()` for creating welcome messages that appear when the chat is empty. Greetings can be set statically via `chat_ui(greeting=)` or dynamically with `Chat.set_greeting()`, and are dismissed when the user sends their first message. A new `{id}_greeting_requested` input fires when the chat is visible, empty, and has no greeting, enabling LLM-generated welcome messages. (#217)

* Added `enable_cancel` parameter to `chat_ui()` and `Chat.ui()` to show a stop button that lets users cancel an in-progress AI response. Press the stop button or hit Escape to cancel. Wire up the `input.<id>_cancel` event to a `chatlas.StreamController` (introduced in chatlas v0.18.0) to connect the UI to your chat provider. (#221)

* Added `footer` parameter to `chat_ui()` and `Chat.ui()` for displaying arbitrary HTML content below the chat input. Useful for disclaimers, attribution, or interactive toolbars. Styled with sensible defaults and customizable via `--shiny-chat-footer-font-size` and `--shiny-chat-footer-color` CSS custom properties. (#224)

* The chat input now supports history navigation: press Up/Down arrow keys when the input is empty to cycle through previously sent messages. Editing a recalled message locks navigation until the input is cleared. (#222)

### Improvements

* Tool result cards now render images and PDFs returned by chatlas tools. When a tool returns `ContentImageInline`, `ContentImageRemote`, or `ContentPDF`, the result is displayed as an inline image or a PDF filename badge. Mixed content lists (e.g., `[ContentText("summary"), content_image_file("plot.png")]`) are rendered with items interleaved in order. Standalone image and PDF content items in turn history are also rendered correctly. (#225)

* Markdown lists where every item is a `<span class="suggestion">` are now rendered as a grid of clickable suggestion cards. Each suggestion's text content becomes both the card label and the value sent on click. To add a short heading above the body text, set the `title` attribute on the span — e.g. `<span class="suggestion" title="Heading">Body text shown on the card.</span>`. Only the body text (not the title) is submitted when the card is clicked. Cards stream in with staggered animations and support keyboard navigation (arrow keys, Home/End) with roving tabindex. (#219)

* Updated minimum `chatlas` version to `>=0.15.0`. (#208)

### Bug fixes

* Fixed a circular import error triggered when `import shinychat` ran before `shiny` had fully initialized. (#212)

* Fixed extra newlines appearing when copying user message text. (#209)


## [0.3.2] - 2026-05-21

### Bug fixes

* Updated for compatibility with htmltools 0.7.0. `split_html_islands` now recognizes the new `TagifiedTag` / `TagifiedTagList` sibling classes when deciding which children carry the `data-shinychat-react` attribute, and `Tool*Component.tagify()` implementations are annotated with `htmltools.Tagified` and return fully-tagified output per the new Tagifiable contract. (#226)

## [0.3.1] - 2026-04-30

### Bug fixes

* Fixed an issue where Shiny UI components (e.g., inputs) passed to `MarkdownStream`'s `content` parameter could fail to initialize, especially on WebKit-based browsers. (#205)

## [0.3.0] - 2026-04-29

### Experimental internal changes

* The chat UI's rendering layer has been migrated from Lit to React. This significantly improves streaming performance — incoming chunks no longer clear previous DOM state — and makes the codebase more maintainable. One trade-off is that certain Shiny UI elements embedded in chat messages may not work as well as before (e.g., inline `<script>` tags are generally not supported inside a React runtime). If you encounter issues, please [let us know](https://github.com/posit-dev/shinychat/issues).

### New features

* Tool result cards now support a fullscreen toggle. Set `full_screen=True` in `ToolResultDisplay()` to add a button that expands the card to fill the viewport. Press `Escape`, click the backdrop, or use the close button to exit fullscreen. (#179)

* Added `footer` parameter to `ToolResultDisplay` for displaying custom HTML content below the tool result card body. (#178)

### Breaking changes

* Removed the deprecated `transform_user` and `transform_assistant` parameters from `.messages()`. As a result, `.messages()` now _always_ returns transformed content (i.e., the result of applying `.transform_user_input()` / `.transform_assistant_response()`, if any), meaning it's better reflection of UI state than LLM-facing message state. This change reflects a greater change in philosophy that `shinychat` shouldn't be managing LLM message state (a backend framework like `chatlas`, `langchain`, `pydantic`, etc. should do this instead). (#193)

* Removed the deprecated `transform` parameter from `.user_input()`. `.user_input()` now always returns the currently stored user message content, which matches the simplified transform handling used by `.messages()`. (#193)

* `ChatMessageDict` (returned by `.messages()`) may now include an `html_deps` key containing serialized `HTMLDependency` dicts. Code that unpacks or iterates these dicts with a fixed set of keys should be updated to handle the new field. (#193)

### Improvements

* Streaming messages now support mid-stream content type transitions. When the content type changes during streaming, previous content is preserved as a frozen segment, maintaining HTML islands and Shiny bindings. (#199)

* Replaced the custom auto-scroll implementation with the `use-stick-to-bottom` library for smoother stick-to-bottom behavior during streaming. A centered "scroll to bottom" button now appears when the user scrolls away from the bottom. (#195)

* Migrated Google provider from the deprecated `google-generativeai` SDK to `google-genai`. (#174)


### Bug fixes

* Fixed some issues with bookmarking. (#188, #192, #193)

* Fixed chat message content touching the right edge of the container. (#197)

* Fixed content inside tool cards (e.g., widgets, plots) not re-laying out when the card is collapsed or expanded. (#180)

* Fixed the chat UI crashing on non-HTTPS contexts (e.g., RStudio Server over plain HTTP) due to `crypto.randomUUID()` being unavailable outside secure contexts. (#186, #187)

* Fixed pyright 1.1.409 compatibility by adding missing `__all__` exports. (#200)

## [0.2.9] - 2026-02-09

### Improvements

* Improved scroll to bottom behavior with tool requests/results. (#157)
* Constrain images in markdown content with max-width: 100%. (#168)

### Maintenance

* Fixed an issue where user chat messages would display the default assistant icon. (#162)

* shinychat now requires Python 3.10 or later and, optionally, langchain 1.0.0 or newer. (#156)

## [0.2.8] - 2025-09-11

### Bug fixes

* Allow `chatlas.types.ToolResultDisplay` to be imported without `pydantic`.

## [0.2.7] - 2025-09-11

### Bug fixes

* Only import `pydantic` if `chatlas` is relevant.

## [0.2.6] - 2025-09-11

### Bug fixes

* `pydantic` is (once again) a soft dependency (included in the `providers` extra).

## [0.2.5] - 2025-09-11

### Bug fixes

* `chatlas` is (once again) a soft dependency (included in the `providers` extra).

## [0.2.4] - 2025-09-10

### Bug fixes

* Fixed an issue (introduced in v0.2.0) where statically rendered messages with HTML dependencies weren't being handled properly. (#134)

## [0.2.3] - 2025-09-10

### Bug fixes

* `message_content()` and `message_content_chunk()` correctly extract content from a `chatlas.Turn`. (#133)

## [0.2.2] - 2025-09-10

### Improvements

* `message_content()` and `message_content_chunk()` can now take `ChatMessage()` as input. (#132)

## [0.2.1] - 2025-09-10

### New features

* `Chat.chat_ui(messages=...)` now supports any type also supported by `message_content()`. (#131)
* `ChatMessage()` can now be constructed outside of a Shiny session. (#131)

## [0.2.0] - 2025-09-10

### New features

* New and improved UI for tool calls that occur via [chatlas](https://posit-dev.github.io/chatlas/). As a reminder, tool call displays are enabled by setting `content="all"` in chatlas' `.stream()` (or `.stream_async()`) method. See the tests under the `pkg-py/tests/playwright/tools` directory for inspiration of what is now possible with custom tool displays via the new `ToolResultDisplay` class. (#107)

* Added new `message_content()` and `message_content_chunk()` generic (`singledispatch`) functions. These functions aren't intended to be called directly by users, but instead, provide an opportunity to teach `Chat.append_message()`/`Chat.append_message_stream()` to extract message contents from different types of objects. (#96)

* External links in chat messages in `chat_ui()` now open in a new tab by default, with a confirmation dialog. (#120)

### Bug fixes

* The chat input no longer submits incomplete text when the user has activated IME completions (e.g. while typing in Japanese or Chinese). (#85)

### Deprecations

* Numerous `Chat()` features have been deprecated in preparation for future removal to simplify the API (#91)
  * `Chat(messages=...)` was deprecated. Use `chat.ui(messages=...)` instead.
  * `Chat(tokenizer=...)` was deprecated. This is only relevant for `.messages(token_limits=...)` which is also now deprecated.
  * All parameters to `.messages()` were deprecated. This reflects an overall change philosophy for maintaining the conversation history sent to the LLM -- `Chat` should no longer be responsible for maintaining it -- another stateful object (perhaps the one provided by chatlas, LangChain, etc.) should be used instead. That said, `.messages()` is still useful if you want to access UI message state.
  * The `.transform_user_input` and `.transform_assistant_response` decorators were deprecated. Instead, transformation of input/responses should be done manually and independently of `Chat`.
  * As a result of the previous deprecations, `.user_input(transform=...)` was also deprecated.

* We consolidated the `<shiny-chat-message>` and `<shiny-user-message>` components into a single `<shiny-chat-message>` component with a `data-role` attribute to indicate whether it's an "assistant" or "user" message. This likely has minimal impact on your apps, other than custom styles. You should update any `shiny-user-message` rules to use `shiny-chat-message[data-role="user"]`. (#101)

## [0.1.0] - 2025-08-07

This first release of the `shinychat` package simply copies the `Chat` and `MarkdownStream` components exactly as they are in version 1.4.0 of `shiny`. Future versions of `shiny` will import these components from `shinychat`. By maintaining these components via a separate library, we can ship features more quickly and independently of `shiny`.
