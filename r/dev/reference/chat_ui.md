# Create a chat UI element

Inserts a chat UI element into a Shiny UI, which includes a scrollable
section for displaying chat messages, and an input field for the user to
enter new messages.

To respond to user input, listen for `input$ID_user_input` (for example,
if `id="my_chat"`, user input will be at `input$my_chat_user_input`),
and use
[`chat_append()`](https://posit-dev.github.io/shinychat/r/dev/reference/chat_append.md)
to append messages to the chat.

## Usage

``` r
chat_ui(
  id,
  ...,
  messages = NULL,
  greeting = NULL,
  placeholder = "Enter a message...",
  width = "min(clamp(680px, 50vw, 760px), 100%)",
  height = "auto",
  fill = TRUE,
  icon_assistant = NULL,
  icon_send = NULL,
  enable_cancel = NULL,
  submit_key = c("enter", "enter+modifier"),
  allow_attachments = NULL,
  toolbar_input = NULL,
  footer = NULL,
  drawer = TRUE,
  show_history = TRUE,
  tool_grouping = c("tool", "none", "all")
)
```

## Arguments

- id:

  The ID of the chat element

- ...:

  Extra HTML attributes to include on the chat element

- messages:

  Deprecated. A list of messages to prepopulate the chat with. Startup
  messages can't be recorded by the conversation-history feature. Use
  `greeting` for a startup message,
  [`chat_append()`](https://posit-dev.github.io/shinychat/r/dev/reference/chat_append.md)
  to replay messages from the server, or set `history = FALSE` in
  [`chat_server()`](https://posit-dev.github.io/shinychat/r/dev/reference/chat_app.md)
  if you're managing conversation state yourself. Each message can be
  one of the following:

  - A string, which is interpreted as markdown and rendered to HTML on
    the client.

    - To prevent interpreting as markdown, mark the string as
      [`htmltools::HTML()`](https://rstudio.github.io/htmltools/reference/HTML.html).

  - A UI element.

    - This includes
      [`htmltools::tagList()`](https://rstudio.github.io/htmltools/reference/tagList.html),
      which takes UI elements (including strings) as children. Strings
      inside a tagList are literal text (HTML-escaped), not markdown.
      Use
      [`htmltools::HTML()`](https://rstudio.github.io/htmltools/reference/HTML.html)
      for trusted raw HTML strings.

  - A named list of `content` and `role`. The `content` can contain
    content as described above, and the `role` can be "assistant" or
    "user".

  - Advanced: a [`list()`](https://rdrr.io/r/base/list.html) mixing bare
    strings and UI elements interleaves markdown and HTML in one
    message, in order. This API is provisional and may change in a
    future release.

- greeting:

  An optional greeting to display when the chat first loads. Can be a
  [`chat_greeting()`](https://posit-dev.github.io/shinychat/r/dev/reference/chat_greeting.md)
  object, or a plain string (which is auto-wrapped with default
  options). The greeting is dismissed when the user sends their first
  message. For example:
  `greeting = chat_greeting("## Hello!\n\nHow can I help you today?")`

- placeholder:

  The placeholder text for the chat's user input field

- width:

  The CSS width of the chat element

- height:

  The CSS height of the chat element

- fill:

  Whether the chat element should try to vertically fill its container,
  if the container is
  [fillable](https://rstudio.github.io/bslib/articles/filling/index.html)

- icon_assistant:

  The icon to use for the assistant chat messages. Can be HTML or a tag
  in the form of
  [`htmltools::HTML()`](https://rstudio.github.io/htmltools/reference/HTML.html)
  or
  [`htmltools::tags()`](https://rstudio.github.io/htmltools/reference/builder.html).
  `NULL` (the default) or `FALSE` omits the assistant icon entirely.
  Pass `TRUE` to use the built-in robot icon (individual messages can
  still opt in to a different icon via the `icon` argument of
  [`chat_append()`](https://posit-dev.github.io/shinychat/r/dev/reference/chat_append.md)).

- icon_send:

  The icon to use for the chat input's ready-state submit button. Can be
  HTML or a tag in the form of
  [`htmltools::HTML()`](https://rstudio.github.io/htmltools/reference/HTML.html)
  or
  [`htmltools::tags()`](https://rstudio.github.io/htmltools/reference/builder.html).
  If `NULL` (the default) or `FALSE`, a default arrow icon is used. The
  button provides a filled circular surface (state-colored background,
  white icon); the supplied icon replaces only the glyph inside it. See
  the "Customizing the send button" section below for styling patterns.

- enable_cancel:

  Whether to show a stop button during streaming that allows the user to
  cancel the in-progress response. When using
  [`chat_server()`](https://posit-dev.github.io/shinychat/r/dev/reference/chat_app.md),
  cancellation is wired up automatically and this defaults to `NULL`
  (let the server decide). For manual usage without
  [`chat_server()`](https://posit-dev.github.io/shinychat/r/dev/reference/chat_app.md),
  set `TRUE` or `FALSE` explicitly and observe `input$<id>_cancel` to
  handle cancellation (e.g., by calling `ctrl$cancel()` on an ellmer
  `stream_controller()`).

- submit_key:

  Controls which key combination submits the chat message. `"enter"`
  (the default): Enter submits, Shift+Enter adds a newline.
  `"enter+modifier"`: Ctrl+Enter (Cmd+Enter on Mac) submits, plain Enter
  adds a newline.

- allow_attachments:

  Controls the file-attachment affordance (an attach button, plus
  clipboard paste and drag-and-drop) in the chat input. `NULL` (default)
  defers to
  [`chat_server()`](https://posit-dev.github.io/shinychat/r/dev/reference/chat_app.md),
  which enables attachments automatically. Pass `TRUE` to accept all
  supported types (PNG, JPEG, GIF, WebP, PDF, and common text/code files
  such as Markdown, plain text, CSV, JSON, and source files), `FALSE` to
  disable, or a character vector of MIME types to restrict what is
  accepted (each must be one of the supported types).

  The shape of `input$<id>_user_input` is determined by this argument,
  so it is predictable for a given app. When attachments are disabled
  (the default), it is the typed text as a character string, exactly as
  before. When attachments are enabled, it is always a list of ellmer
  [ellmer::Content](https://ellmer.tidyverse.org/reference/Content.html)
  objects (the typed text, if any, followed by one content object per
  attachment) - a list even when no files were attached. Splice the list
  into a chat method's `...` with `!!!`, e.g.
  `client$stream_async(!!!input$<id>_user_input)`. (No
  [`rlang::inject()`](https://rlang.r-lib.org/reference/inject.html) is
  needed: ellmer's chat methods collect `...` with dynamic dots.)

  The maximum combined size of all attachments in a single message is
  controlled globally by the `SHINYCHAT_MAX_ATTACHMENT_SIZE` environment
  variable (a raw byte count; defaults to approximately 30 MB). Files
  that would push the total over this cap are rejected in the browser
  with a notice.

- toolbar_input:

  Optional HTML content to display directly below the chat input. Use
  [`bslib::toolbar()`](https://rstudio.github.io/bslib/reference/toolbar.html)
  to group toolbar controls.

- footer:

  Optional HTML content to display in a bottom-pinned, full-width chat
  region. This can be any HTML content (tags, tag lists, or character
  strings). Useful for adding disclaimers, attribution, or other
  information. The footer text is styled slightly smaller and lighter
  than body text by default. Customize with CSS properties
  `--shiny-chat-footer-font-size` and `--shiny-chat-footer-color` on the
  chat container or footer element.

- drawer:

  Whether to enable the drawer. `TRUE` (the default) enables an
  initially hidden panel with default options, `FALSE` omits it, and
  [`chat_drawer()`](https://posit-dev.github.io/shinychat/r/dev/reference/chat_drawer.md)
  supplies its initial configuration.

- show_history:

  Whether to show the built-in history selector. Defaults to `TRUE`;
  setting it to `FALSE` only hides its presentation.

- tool_grouping:

  Controls how tool calls are grouped together in the compact activity
  rows:

  - `"tool"` (default): calls to the *same* tool within a turn's
    contiguous tool loop are grouped into one activity row. This groups
    by tool name across the whole loop, not just consecutive calls –
    e.g. calls to tools `X`, `Y`, `Z`, `X`, `Y` (in that order) are
    grouped into `X` (2 calls), `Y` (2 calls), and `Z` (1 call).

  - `"all"`: every tool call within a contiguous tool loop is summarized
    in one activity row, regardless of tool name.

  - `"none"`: each tool call is shown in its own activity row. Its
    request and result remain available by drilling into that row; this
    does not restore an always-visible card stack.

  Prose or thinking between tool calls starts a new tool loop, so calls
  on opposite sides of either boundary never group together. Individual
  tools can override `"tool"` or `"all"` via a top-level `grouping` tool
  annotation, e.g.
  `ellmer::tool(..., annotations = ellmer::tool_annotations(grouping = "all"))`.
  `tool_grouping = "none"` takes precedence over every annotation and
  disables grouping for the whole chat.

## Value

A Shiny tag object, suitable for inclusion in a Shiny UI

## Pairing with [`chat_server()`](https://posit-dev.github.io/shinychat/r/dev/reference/chat_app.md)

`chat_ui(id)` and `chat_server(id, client)` pair by matching `id`. This
works the same way at the top level of an app and inside your own Shiny
module —
[`chat_server()`](https://posit-dev.github.io/shinychat/r/dev/reference/chat_app.md)
is not itself a module, so no `NS(id, "chat")` wrapping is required:

    # Top-level app, no module
    ui <- page_fillable(chat_ui("chat"))
    server <- function(input, output, session) {
      chat_server("chat", client)
    }

    # Inside your own module: pass the same literal id to both, and call
    # chat_server() from inside moduleServer() so it inherits the module's
    # already-namespaced `session`
    mod_ui <- function(id) {
      ns <- NS(id)
      chat_ui(ns("chat"))
    }
    mod_server <- function(id, client) {
      moduleServer(id, function(input, output, session) {
        chat_server("chat", client)
      })
    }

## Greeting

A greeting is an optional welcome message shown before any conversation
messages. It is automatically dismissed when the user sends their first
message (unless created with `persistent = TRUE`).

**Static greeting.** Pass a string or
[`chat_greeting()`](https://posit-dev.github.io/shinychat/r/dev/reference/chat_greeting.md)
to the `greeting` parameter:

    chat_ui("chat", greeting = "## Hello!\n\nHow can I help you today?")

**Dynamic greeting from the server.** Leave `greeting` unset and use
[`chat_set_greeting()`](https://posit-dev.github.io/shinychat/r/dev/reference/chat_set_greeting.md)
from your server function. This is useful when the greeting depends on
session state or is generated by a model.

**`greeting_requested` input.** When the chat is visible on the page,
has no messages, and has no greeting set, Shiny fires
`input$<id>_greeting_requested` (e.g. `input$chat_greeting_requested`
for `chat_ui("chat")`). The value is an event counter suitable for
[`shiny::observeEvent()`](https://rdrr.io/pkg/shiny/man/observeEvent.html).
Use it to trigger server-side greeting generation:

    observeEvent(input$chat_greeting_requested, {
      stream <- chat_client$stream_async("Generate a short welcome message.")
      chat_set_greeting("chat", chat_greeting(stream))
    })

This input fires when the chat component is first viewed on the page and
empty, and again after
[`chat_clear()`](https://posit-dev.github.io/shinychat/r/dev/reference/chat_clear.md)
`(greeting = TRUE)`, enabling a regenerate pattern where clearing the
greeting automatically triggers a fresh one.

**`greeting_dismissed` input.** When the user dismisses the greeting,
`input$<id>_greeting_dismissed` fires with a `Date.now()` timestamp. If
the greeting is later cleared after being dismissed, the input resets to
`NULL`. If you use
[`chat_server()`](https://posit-dev.github.io/shinychat/r/dev/reference/chat_app.md),
you can access the `greeting_dismissed` reactive from the returned value
instead of the raw namespaced input string.

## Thinking display

When a model produces reasoning or "thinking" tokens, shinychat renders
them in a collapsible panel above the response. The panel shows a live
stream of the model's reasoning while it thinks, then auto-collapses
when the response begins.

Thinking display works automatically with any model that supports it.
Two paths are supported:

1.  **ellmer's `ContentThinking` objects.** Models that provide a
    structured thinking API (e.g., Claude with extended thinking) emit
    `ContentThinking` objects when you stream with `stream = "content"`.
    shinychat detects these and routes them to the thinking panel. This
    is what
    [`chat_append()`](https://posit-dev.github.io/shinychat/r/dev/reference/chat_append.md)
    uses internally when you pass it an ellmer content stream.

2.  **Raw `<thinking>` tags.** Many open-source and local models
    (DeepSeek, QwQ, Qwen, etc.) emit `<thinking>...</thinking>` tags
    directly in their markdown output. shinychat detects these tags
    during streaming and renders the enclosed text in the thinking panel
    with no extra configuration.

### Topic labels

You can optionally get labeled sub-sections within the thinking panel by
asking the model to emit `<topic>...</topic>` tags in its reasoning.
These are extracted and rendered as section headings inside the thinking
display, and the current topic appears in the collapsed header as a live
status.

To use topic labels, add something like this to your system prompt:

    When thinking through a problem, wrap brief topic labels in <topic> tags
    to indicate what you're currently reasoning about. For example:
    <topic>parsing the input</topic>

Topic labels are entirely optional. Without them, the thinking panel
still works – it just won't have sub-section headings.

## Customizing the send button

The send button is a filled circle (24px by default) whose background
color reflects the current state (primary when ready, gray when
empty/disabled, danger when cancelling) with a white icon (22px by
default) centered inside. The `icon_send` parameter swaps the
ready-state icon without changing the button's surface.

**Custom icon.** Pass an SVG from
[`bsicons::bs_icon()`](https://rdrr.io/pkg/bsicons/man/bs_icon.html) or
`faicons::icon_svg()`. The button provides the surface, so a bare glyph
gets the same filled-circle treatment as the default arrow:

    chat_ui("chat", icon_send = bsicons::bs_icon("send-fill"))

**Icon with text.** Use
[`htmltools::tagList()`](https://rstudio.github.io/htmltools/reference/tagList.html)
to pass an icon and a text label as siblings (not wrapped in a `<span>`)
so they lay out side by side, with a Bootstrap margin utility for
spacing. Then override the button to size to its content instead of the
default fixed circle:

    chat_ui("chat",
      icon_send = tagList(
        bsicons::bs_icon("airplane-fill"),
        span("Send", class = "ms-2")
      )
    )

    :root .shiny-chat-btn-send {
      width: auto;
      height: auto;
      padding: 4px 10px;
      border-radius: 6px;
    }

**Per-state color overrides.** Each state's color can be set
independently via CSS variables on the chat container or any ancestor.
These are only read by the component (never set on the button), so
inline styles inherit cleanly:

    #chat {
      --shiny-chat-btn-send-color-cancel: #abc123;
    }

**Ghost (outline) style.** Make the button transparent at rest with the
state color on the icon and border, filling on hover. Target the button
element (not an ancestor) because the internal `--_btn-send-state-color`
variable resolves on the button itself:

    :root .shiny-chat-btn-send {
      --shiny-chat-btn-send-bg: transparent;
      --shiny-chat-btn-send-color: var(--_btn-send-state-color);
      --shiny-chat-btn-send-border: 1px solid var(--_btn-send-state-color);
      --shiny-chat-btn-send-color-hover: #fff;
      --shiny-chat-btn-send-bg-hover: var(--_btn-send-state-color);
    }

**Key CSS variables:**

- `--shiny-chat-btn-send-size` — Button width and height (default
  `24px`)

- `--shiny-chat-input-icon-size` — Icon size, shared with the attach
  button (default `22px`)

- `--shiny-chat-btn-send-bg` — Button background (default: state color)

- `--shiny-chat-btn-send-color` — Icon color (default: `#fff`)

- `--shiny-chat-btn-send-border` — Button border (default: `none`)

- `--shiny-chat-btn-send-color-ready` — Override ready/pending color
  (default: `--bs-primary`)

- `--shiny-chat-btn-send-color-empty` — Override empty/disabled color
  (default: `--bs-gray-500`)

- `--shiny-chat-btn-send-color-cancel` — Override cancel/cancelling
  color (default: `--bs-danger`)

## Examples

``` r
if (FALSE) { # interactive()
library(shiny)
library(bslib)
library(shinychat)

ui <- page_fillable(
  chat_ui("chat", fill = TRUE)
)

server <- function(input, output, session) {
  observeEvent(input$chat_user_input, {
    # In a real app, this would call out to a chat client or API,
    # perhaps using the 'ellmer' package.
    response <- paste0(
      "You said:\n\n",
      "<blockquote>",
      htmltools::htmlEscape(input$chat_user_input),
      "</blockquote>"
    )
    chat_append("chat", response)
  })
}

shinyApp(ui, server)
}
```
