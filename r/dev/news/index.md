# Changelog

## shinychat (development version)

### New features and improvements

- Web search and web fetch responses from ellmer now show their activity
  and citations directly in the chat. Readers can open a citation beside
  its claim or use the message-wide Sources pill.
  `ContentCitation@grounded_span` links each citation to the answer text
  that it supports.

- Assistant messages can now attach source details to specific claims
  with the `<shiny-aside>` markup convention. This convention powers
  shinychat’s web citations and can also support custom RAG workflows.
  Add an inline `<shiny-aside>` tag with source details and an optional
  `grounded-span`. Shinychat shows a compact source pill and highlights
  the related text when the pill is open. See the `Asides` section in
  [`?chat_append`](https://posit-dev.github.io/shinychat/r/dev/reference/chat_append.md).

- Tool calls now render as a condensed activity row by default. Expand a
  group row to see each individual call, then drill into a call to see
  its full request/result card. Added
  [`tool_result_display()`](https://posit-dev.github.io/shinychat/r/dev/reference/tool_result_display.md),
  a validated constructor for the `display` object passed as
  `extra = list(display = tool_result_display(...))` on an
  [`ellmer::ContentToolResult`](https://ellmer.tidyverse.org/reference/Content.html)
  – the recommended way to build it going forward. A bare named list
  with the same fields still works and is promoted internally.
  [`tool_result_display()`](https://posit-dev.github.io/shinychat/r/dev/reference/tool_result_display.md)
  gained `label` (a short per-call identifying value, e.g. a filename or
  query) and `value_preview` (a terse peek at the result, e.g. “1,204
  rows”), both shown in the activity row.

- Fully custom tool-result UI returned from a
  [`contents_shinychat()`](https://posit-dev.github.io/shinychat/r/dev/reference/contents_shinychat.md)
  method is now paired with its tool request. While the tool runs, it
  appears in the activity row; after the custom result settles, that
  call leaves the row and the custom UI renders as standalone output.
  This also preserves custom results when preloading or restoring
  conversations.

- Added `tool_grouping` to
  [`chat_ui()`](https://posit-dev.github.io/shinychat/r/dev/reference/chat_ui.md):
  `"tool"` (default) groups calls to the same tool in a contiguous tool
  loop (order-independent, not just consecutive calls); `"all"` groups
  every call in the loop together; `"none"` shows one activity row per
  call. Thinking or prose starts a new loop, and chat-level `"none"`
  disables grouping even when an annotation asks for it. Individual
  tools can override `"tool"` or `"all"` with a top-level `grouping`
  tool annotation,
  e.g. `tool(..., annotations = tool_annotations(grouping = "all"))`.

- Added
  [`chat_server()`](https://posit-dev.github.io/shinychat/r/dev/reference/chat_app.md)
  as the new primary way to wire up server-side chat logic. Pair it with
  [`chat_ui()`](https://posit-dev.github.io/shinychat/r/dev/reference/chat_ui.md)
  by matching `id`, e.g. `chat_ui("chat")` with
  `chat_server("chat", client)`. It does the same job as
  [`chat_mod_server()`](https://posit-dev.github.io/shinychat/r/dev/reference/chat_mod_ui.md)
  but runs directly in the caller’s session scope rather than creating
  its own module scope. If you’re already inside a
  [`moduleServer()`](https://rdrr.io/pkg/shiny/man/moduleServer.html),
  pass that session in.
  [`chat_mod_server()`](https://posit-dev.github.io/shinychat/r/dev/reference/chat_mod_ui.md)
  and
  [`chat_mod_ui()`](https://posit-dev.github.io/shinychat/r/dev/reference/chat_mod_ui.md)
  are now soft-deprecated in favor of
  [`chat_server()`](https://posit-dev.github.io/shinychat/r/dev/reference/chat_app.md)
  and
  [`chat_ui()`](https://posit-dev.github.io/shinychat/r/dev/reference/chat_ui.md).
  ([\#264](https://github.com/posit-dev/shinychat/issues/264))

- [`chat_server()`](https://posit-dev.github.io/shinychat/r/dev/reference/chat_app.md)
  gets multi-conversation history automatically: a drawer for starting
  new chats and returning to previous ones, with LLM-generated titles,
  search, rename, and delete. Conversations are persisted per-user (or a
  custom scope) via a pluggable store — the default
  `FileConversationStore` finds a redeploy-safe location automatically
  on Posit Connect. Customize with `history = history_options(...)`, or
  opt out entirely with `history = FALSE`. For apps that can’t use the
  module pattern, wire it up manually with
  [`chat_enable_history()`](https://posit-dev.github.io/shinychat/r/dev/reference/chat_enable_history.md).
  ([\#266](https://github.com/posit-dev/shinychat/issues/266))

  - `history_options(restore_mode = )` controls how the active
    conversation is remembered across page reloads: `"browser"`
    (default) via `localStorage`, `"url"` via a
    `?shinychat_conversation_id=` query parameter, `"bookmark"` via full
    Shiny server bookmarking (requires `bookmarkStore = "server"`, and
    also restores raw input controls), or `"none"` to disable. Use the
    `on_save`/`on_restore` arguments of
    [`chat_enable_history()`](https://posit-dev.github.io/shinychat/r/dev/reference/chat_enable_history.md)
    (or `on_save()`/`on_restore()` on the `history` object returned by
    [`chat_server()`](https://posit-dev.github.io/shinychat/r/dev/reference/chat_app.md))
    to keep other app state synced to the active conversation.
    ([\#266](https://github.com/posit-dev/shinychat/issues/266))

- Added file attachment support: users can upload images, PDFs, and text
  files alongside chat messages via a file picker button, drag-and-drop,
  or clipboard paste.
  [`chat_server()`](https://posit-dev.github.io/shinychat/r/dev/reference/chat_app.md)
  enables attachments by default and automatically convert uploads into
  ellmer `Content` objects for the model. For
  non-[`chat_server()`](https://posit-dev.github.io/shinychat/r/dev/reference/chat_app.md)
  usage, enable with `allow_attachments = TRUE` (or a MIME allow-list)
  and splice `input$<id>_user_input` into chat methods with `!!!`. The
  maximum combined attachment size defaults to approximately 30 MB and
  can be configured via the `SHINYCHAT_MAX_ATTACHMENT_SIZE` environment
  variable.

- Added slash commands: a typeahead command palette that lets users
  trigger named shortcuts directly from the chat input. Type `/` to open
  the palette, filter by typing, and pick a command with arrow keys or
  click. Commands can expand into LLM prompts, trigger server-side side
  effects (clear chat, open a modal, export transcript), or be handled
  entirely client-side via the cancelable `shiny:chat-slash-command` DOM
  event. Register commands with `chat$slash_command()`, which accepts 0-
  or 1-argument handlers; 1-argument handlers receive a
  `ContentSlashCommand` object (a `ContentText` subclass with `command`
  and `user_text` slots) so handlers can mutate `content@text` before
  passing it to `client$stream()`. The `echo` parameter controls whether
  an invocation is recorded as a user message and triggers a loading
  state. Echoed commands are faithfully restored on bookmark/restore.
  ([\#239](https://github.com/posit-dev/shinychat/issues/239))

- Added `submit_key` parameter to
  [`chat_ui()`](https://posit-dev.github.io/shinychat/r/dev/reference/chat_ui.md):
  `"enter"` (default, Enter submits) or `"enter+modifier"`
  (Ctrl/Cmd+Enter submits, plain Enter inserts a line break). The input
  remains editable while a response is streaming — only submission is
  blocked, not typing.
  ([\#251](https://github.com/posit-dev/shinychat/issues/251))

### Breaking changes

- The CSS classes used by the external-link dialog, thinking display,
  and tool-result images/PDFs now use the `.shiny-chat-*` prefix instead
  of `.shinychat-*`. The thinking display’s custom properties and
  animation names have likewise changed from `--shinychat-thinking-*` /
  `shinychat-thinking-*` to `--shiny-chat-thinking-*` /
  `shiny-chat-thinking-*`. Update any custom CSS that targets these
  identifiers.
  ([\#285](https://github.com/posit-dev/shinychat/issues/285),
  [\#286](https://github.com/posit-dev/shinychat/issues/286))

- A tool’s definition `title` (from its annotations) and its result
  `title` (from
  [`tool_result_display()`](https://posit-dev.github.io/shinychat/r/dev/reference/tool_result_display.md))
  are now shown as-is, without any client-side tense conjugation. The
  definition title is shown while the call is running and labels
  multi-call groups. For a single-call row, the result title (if
  provided) replaces it when the result arrives; in a multi-call group,
  a distinct result title can identify that call in the expanded list.
  The old `"Running {title}"` / `"{title} failed"` client-side title
  template has been removed. If a tool’s title reads oddly while running
  now that the automatic “Running” prefix is gone, write an explicit
  present-tense definition title (e.g. “Running R code”) and,
  optionally, a past-tense result title (e.g. “Ran R code”). Failures
  are shown via a separate status cue (a “failed”/“N failed” note and
  icon) rather than appended to the title.

- `input$<id>_user_input` now depends on `allow_attachments`. With
  `allow_attachments = FALSE`, it remains the historical typed string.
  With attachments enabled (`TRUE` or a MIME allow-list), it is always a
  list of ellmer `Content` objects (typed text, if present, followed by
  one object per attachment), and the separate
  `input$<id>_user_attachments` input has been removed. Forward either
  form to a chat method by splicing with `!!!`,
  e.g. `chat$stream_async(!!!input$<id>_user_input)`.

- The `last_input` reactive returned by
  [`chat_server()`](https://posit-dev.github.io/shinychat/r/dev/reference/chat_app.md)
  now mirrors the shape of `input$<id>_user_input`: a string when
  attachments are disabled, and a list of ellmer `Content` objects when
  enabled.

- `input$<id>_user_input` is now a persistent regular input rather than
  an event input, so it retains its last submitted value between
  submissions instead of resetting to `NULL`. This lets it co-batch with
  the client’s message snapshot in a single reactive flush. It remains
  excluded from bookmarks.

### Bug fixes

- Fixed a race between the chat greeting and conversation history
  restore: reloading a page that restored a previous conversation could
  briefly flash the app’s greeting, and starting a new chat after a
  session began with a restored conversation could fail to show any
  greeting at all. Greeting resolution now defers to history’s own
  restore decision instead of racing the client’s independent greeting
  request.

- Fixed
  [`output_markdown_stream()`](https://posit-dev.github.io/shinychat/r/dev/reference/output_markdown_stream.md)
  permanently stopping following new content after the user scrolled
  back to the bottom. Pinning was decided only from `scroll` events,
  which browsers dispatch asynchronously; if a chunk grew the container
  first, the user’s at-bottom position no longer read as at-bottom and
  auto-scroll silently disengaged for good.
  ([\#282](https://github.com/posit-dev/shinychat/issues/282))

- [`chat_app()`](https://posit-dev.github.io/shinychat/r/dev/reference/chat_app.md)
  no longer renders a close button or registers a
  [`stopApp()`](https://rdrr.io/pkg/shiny/man/stopApp.html) observer
  when deployed to a server. Both are now gated on
  [`rlang::is_interactive()`](https://rlang.r-lib.org/reference/is_interactive.html),
  preventing session crashes in multi-user deployments.
  ([\#265](https://github.com/posit-dev/shinychat/issues/265))

- The `dismissible` parameter of
  [`chat_greeting()`](https://posit-dev.github.io/shinychat/r/dev/reference/chat_greeting.md)
  has been renamed to `persistent` with an inverted value.
  `dismissible = FALSE` (greeting stays visible) is now
  `persistent = TRUE`. The old `dismissible` argument still works but
  warns. When both `persistent` and `dismissible` are provided,
  `persistent` now takes precedence silently rather than erroring.
  ([\#260](https://github.com/posit-dev/shinychat/issues/260))

- Fixed suggestion cards and the greeting overflowing the chat container
  in narrow spaces such as sidebars.
  ([\#255](https://github.com/posit-dev/shinychat/issues/255))

- Fixed the copy button on code blocks not working in some embedded
  contexts. ([@thisisnic](https://github.com/thisisnic),
  [\#247](https://github.com/posit-dev/shinychat/issues/247))

## shinychat 0.4.0

CRAN release: 2026-06-01

### Experimental internal changes

- The chat UI’s rendering layer has been migrated from Lit to React.
  This significantly improves streaming performance — incoming chunks no
  longer clear previous DOM state — and makes the codebase more
  maintainable. One trade-off is that certain Shiny UI elements embedded
  in chat messages may not work as well as before (e.g., inline
  `<script>` tags are generally not supported inside a React runtime).
  If you encounter issues, please [let us
  know](https://github.com/posit-dev/shinychat/issues).

### New features and improvements

- The chat UI now displays model reasoning/thinking content as
  collapsible panels above assistant responses. Thinking content streams
  in real-time with animated topic labels. This works with providers
  that support structured thinking (e.g., Claude’s extended thinking via
  `ellmer`) and with local models that wrap reasoning in `<thinking>`
  tags. ([\#208](https://github.com/posit-dev/shinychat/issues/208))

- Added `enable_cancel` parameter to
  [`chat_ui()`](https://posit-dev.github.io/shinychat/r/dev/reference/chat_ui.md)
  to show a stop button that lets users cancel an in-progress AI
  response. Press the stop button or hit Escape to cancel.
  [`chat_mod_ui()`](https://posit-dev.github.io/shinychat/r/dev/reference/chat_mod_ui.md)
  enables cancellation by default, and
  [`chat_mod_server()`](https://posit-dev.github.io/shinychat/r/dev/reference/chat_mod_ui.md)
  handles the cancellation wiring automatically, using the stream
  cancellation features introduced in ellmer v0.4.1.
  ([\#221](https://github.com/posit-dev/shinychat/issues/221))

- Markdown lists where every item is a `<span class="suggestion">` are
  now rendered as a grid of clickable suggestion cards. Each
  suggestion’s text content becomes both the card label and the value
  sent on click. To add a short heading above the body text, set the
  `title` attribute on the span —
  e.g. `<span class="suggestion" title="Heading">Body text shown on the card.</span>`.
  Only the body text (not the title) is submitted when the card is
  clicked. Cards stream in with staggered animations and support
  keyboard navigation (arrow keys, Home/End) with roving tabindex.
  ([\#219](https://github.com/posit-dev/shinychat/issues/219))

- Added
  [`chat_greeting()`](https://posit-dev.github.io/shinychat/r/dev/reference/chat_greeting.md)
  for creating welcome messages that appear when the chat is empty.
  Greetings can be set statically via `chat_ui(greeting=)` or
  dynamically from the server with
  [`chat_set_greeting()`](https://posit-dev.github.io/shinychat/r/dev/reference/chat_set_greeting.md).
  They are automatically dismissed when the user sends their first
  message. A new `greeting_requested` input fires when the chat is
  visible, empty, and has no greeting, enabling LLM-generated welcome
  messages. `chat_mod_server(greeting=)` accepts a function for
  auto-generated greetings.
  ([\#217](https://github.com/posit-dev/shinychat/issues/217))

- Tool result cards now render images and PDFs returned by ellmer tools.
  When a tool returns
  [`content_image_file()`](https://ellmer.tidyverse.org/reference/content_image_url.html),
  [`content_image_url()`](https://ellmer.tidyverse.org/reference/content_image_url.html),
  or
  [`content_pdf_file()`](https://ellmer.tidyverse.org/reference/content_pdf_file.html),
  the result is displayed as an inline image or a PDF filename badge.
  Mixed content lists (e.g.,
  `list(ContentText("summary"), content_image_file("plot.png"))`) are
  rendered with items interleaved in order.
  ([\#225](https://github.com/posit-dev/shinychat/issues/225))

- Added `footer` parameter to
  [`chat_ui()`](https://posit-dev.github.io/shinychat/r/dev/reference/chat_ui.md)
  for displaying arbitrary HTML content below the chat input. Useful for
  disclaimers, attribution, or interactive toolbars. Styled with
  sensible defaults and customizable via `--shiny-chat-footer-font-size`
  and `--shiny-chat-footer-color` CSS custom properties.
  ([\#224](https://github.com/posit-dev/shinychat/issues/224))

- Tool result cards now support a fullscreen toggle. Set
  `full_screen = TRUE` in the `display` list (or set
  `res$full_screen <- NA` in a custom
  [`contents_shinychat()`](https://posit-dev.github.io/shinychat/r/dev/reference/contents_shinychat.md)
  method) to add a button that expands the card to fill the viewport.
  Press `Escape`, click the backdrop, or use the close button to exit
  fullscreen.

- Added `footer` field to `ToolResultDisplay` for displaying custom HTML
  content below the tool result card body.
  ([\#178](https://github.com/posit-dev/shinychat/issues/178))

- [`chat_mod_server()`](https://posit-dev.github.io/shinychat/r/dev/reference/chat_mod_ui.md)
  now returns a `set_client(new_client, sync = TRUE)` function for
  swapping the chat client used by the module at runtime. When
  `sync = TRUE` (the default), the new client inherits the current
  conversation’s turns, system prompt, and tools so the conversation
  continues seamlessly. If a response is currently streaming, the swap
  is deferred until the stream completes.
  ([\#227](https://github.com/posit-dev/shinychat/issues/227))

- [`chat_mod_server()`](https://posit-dev.github.io/shinychat/r/dev/reference/chat_mod_ui.md)
  now returns a `status` reactive that reports the current interaction
  state: `"idle"` when no response is in progress, or `"streaming"`
  while a response is actively being received.
  ([\#227](https://github.com/posit-dev/shinychat/issues/227))

- [`chat_restore()`](https://posit-dev.github.io/shinychat/r/dev/reference/chat_restore.md)
  now invisibly returns a cancel function that tears down all bookmark
  registrations made by that call. This is useful when swapping the chat
  client via `set_client()`, which handles the re-registration
  automatically.
  ([\#227](https://github.com/posit-dev/shinychat/issues/227))

### Improvements

- All navigating links in assistant messages now open in a new tab to
  preserve the app’s session state. Cross-origin links still show the
  confirmation dialog; same-origin links open directly.
  ([\#238](https://github.com/posit-dev/shinychat/issues/238))

### Bug fixes

- Fixed the external link confirmation dialog not rendering in Safari.
  The backdrop overlay appeared but the dialog content was invisible due
  to a Bootstrap/`<dialog>` CSS interaction.
  ([\#201](https://github.com/posit-dev/shinychat/issues/201),
  [\#238](https://github.com/posit-dev/shinychat/issues/238))

- Fixed pressing Escape to dismiss the external link dialog leaving it
  in a broken state where subsequent link clicks no longer worked.
  ([\#238](https://github.com/posit-dev/shinychat/issues/238))

- Fixed an issue where user chat messages would display the default
  assistant icon.
  ([\#162](https://github.com/posit-dev/shinychat/issues/162))

## shinychat 0.3.0

CRAN release: 2025-11-20

### Breaking changes

- [`chat_mod_server()`](https://posit-dev.github.io/shinychat/r/dev/reference/chat_mod_ui.md)
  now returns a list of reactives for `last_input` and `last_turn`, as
  well functions to `update_user_input()`,
  [`append()`](https://rdrr.io/r/base/append.html) and `clear()` the
  chat. ([\#130](https://github.com/posit-dev/shinychat/issues/130),
  [\#143](https://github.com/posit-dev/shinychat/issues/143),
  [\#145](https://github.com/posit-dev/shinychat/issues/145))

### New features

- Added
  [`chat_restore()`](https://posit-dev.github.io/shinychat/r/dev/reference/chat_restore.md)
  which adds Shiny bookmarking hooks to save and restore the
  [ellmer](https://ellmer.tidyverse.org) chat client.
  ([\#28](https://github.com/posit-dev/shinychat/issues/28),
  [\#82](https://github.com/posit-dev/shinychat/issues/82))

- Added
  [`update_chat_user_input()`](https://posit-dev.github.io/shinychat/r/dev/reference/update_chat_user_input.md)
  for programmatically updating the user input of a chat UI element.
  ([\#78](https://github.com/posit-dev/shinychat/issues/78))

- shinychat now shows tool call request and results in the UI, and the
  feature is enabled by default in
  [`chat_app()`](https://posit-dev.github.io/shinychat/r/dev/reference/chat_app.md)
  and the chat module
  ([`chat_mod_server()`](https://posit-dev.github.io/shinychat/r/dev/reference/chat_mod_ui.md)).
  When using
  [`chat_append()`](https://posit-dev.github.io/shinychat/r/dev/reference/chat_append.md)
  with
  [`chat_ui()`](https://posit-dev.github.io/shinychat/r/dev/reference/chat_ui.md),
  set `stream = "content"` when you call the `$stream_async()` method on
  the [`ellmer::Chat`](https://ellmer.tidyverse.org/reference/Chat.html)
  client to ensure tool calls are included in the chat stream output.
  Learn more in the [tool calling UI
  article](https://posit-dev.github.io/shinychat/r/articles/tool-ui.html).
  ([\#52](https://github.com/posit-dev/shinychat/issues/52))

- Added `chat_append(icon=...)` and `chat_ui(icon_assistant=...)` for
  customizing the icon that appears next to assistant responses.
  ([\#88](https://github.com/posit-dev/shinychat/issues/88))

### Improvements

- [`chat_app()`](https://posit-dev.github.io/shinychat/r/dev/reference/chat_app.md)
  now correctly restores the chat client state when refreshing the app,
  e.g. by reloading the page.
  ([\#71](https://github.com/posit-dev/shinychat/issues/71))

- External links in chat messages in
  [`chat_ui()`](https://posit-dev.github.io/shinychat/r/dev/reference/chat_ui.md)
  now open in a new tab by default, with a confirmation dialog.
  ([\#120](https://github.com/posit-dev/shinychat/issues/120))

### Bug fixes

- The chat input no longer submits incomplete text when the user has
  activated IME completions (e.g. while typing in Japanese or Chinese).
  ([\#85](https://github.com/posit-dev/shinychat/issues/85))

### Internal changes

- We consolidated the `<shiny-chat-message>` and `<shiny-user-message>`
  components into a single `<shiny-chat-message>` component with a
  `data-role` attribute to indicate whether it’s an “assistant” or
  “user” message. This likely has minimal impact on your apps, other
  than custom styles. You should update any `shiny-user-message` rules
  to use `shiny-chat-message[data-role="user"]`.
  ([\#101](https://github.com/posit-dev/shinychat/issues/101))

- The chat UI’s send input button is now identified by the class
  `.shiny-chat-btn-send`.
  ([@DeepanshKhurana](https://github.com/DeepanshKhurana),
  [\#138](https://github.com/posit-dev/shinychat/issues/138))

## shinychat 0.2.0

CRAN release: 2025-05-16

### New features and improvements

- Added new
  [`output_markdown_stream()`](https://posit-dev.github.io/shinychat/r/dev/reference/output_markdown_stream.md)
  and
  [`markdown_stream()`](https://posit-dev.github.io/shinychat/r/dev/reference/markdown_stream.md)
  functions to allow for streaming markdown content to the client. This
  is useful for showing Generative AI responses in real-time in a Shiny
  app, outside of a chat interface.
  ([\#23](https://github.com/posit-dev/shinychat/issues/23))

- Both
  [`chat_ui()`](https://posit-dev.github.io/shinychat/r/dev/reference/chat_ui.md)
  and
  [`output_markdown_stream()`](https://posit-dev.github.io/shinychat/r/dev/reference/output_markdown_stream.md)
  now support arbitrary Shiny UI elements inside of messages. This
  allows for gathering input from the user (e.g.,
  [`selectInput()`](https://rdrr.io/pkg/shiny/man/selectInput.html)),
  displaying of rich output (e.g.,
  [htmlwidgets](https://github.com/ramnathv/htmlwidgets) like
  [plotly](https://plotly-r.com)), and more.
  ([\#29](https://github.com/posit-dev/shinychat/issues/29))

- Added a new
  [`chat_clear()`](https://posit-dev.github.io/shinychat/r/dev/reference/chat_clear.md)
  function to clear the chat of all messages.
  ([\#25](https://github.com/posit-dev/shinychat/issues/25))

- Added
  [`chat_app()`](https://posit-dev.github.io/shinychat/r/dev/reference/chat_app.md),
  [`chat_mod_ui()`](https://posit-dev.github.io/shinychat/r/dev/reference/chat_mod_ui.md)
  and
  [`chat_mod_server()`](https://posit-dev.github.io/shinychat/r/dev/reference/chat_mod_ui.md).
  [`chat_app()`](https://posit-dev.github.io/shinychat/r/dev/reference/chat_app.md)
  takes an [ellmer](https://ellmer.tidyverse.org) chat client and
  launches a simple Shiny app interface with the chat.
  [`chat_mod_ui()`](https://posit-dev.github.io/shinychat/r/dev/reference/chat_mod_ui.md)
  and
  [`chat_mod_server()`](https://posit-dev.github.io/shinychat/r/dev/reference/chat_mod_ui.md)
  replicate the interface as a Shiny module, for easily adding a simple
  chat interface connected to a specific
  [ellmer](https://ellmer.tidyverse.org) chat client.
  ([\#36](https://github.com/posit-dev/shinychat/issues/36))

- The promise returned by
  [`chat_append()`](https://posit-dev.github.io/shinychat/r/dev/reference/chat_append.md)
  now resolves to the content streamed into the chat.
  ([\#49](https://github.com/posit-dev/shinychat/issues/49))

### Bug fixes

- [`chat_append()`](https://posit-dev.github.io/shinychat/r/dev/reference/chat_append.md),
  [`chat_append_message()`](https://posit-dev.github.io/shinychat/r/dev/reference/chat_append_message.md)
  and
  [`chat_clear()`](https://posit-dev.github.io/shinychat/r/dev/reference/chat_clear.md)
  now all work in Shiny modules without needing to namespace the `id` of
  the Chat component.
  ([\#37](https://github.com/posit-dev/shinychat/issues/37))

- [`chat_append()`](https://posit-dev.github.io/shinychat/r/dev/reference/chat_append.md)
  now logs and throws a silent error if the stream errors for any
  reason. This prevents the app from crashing if the stream is
  interrupted. You can still use
  [`promises::catch()`](https://rstudio.github.io/promises/reference/then.html)
  to handle the error in your app code if desired.
  ([\#46](https://github.com/posit-dev/shinychat/issues/46))

## shinychat 0.1.1

CRAN release: 2024-12-18

- Initial CRAN submission.
