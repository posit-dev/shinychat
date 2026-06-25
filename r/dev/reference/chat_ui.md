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
  width = "min(680px, 100%)",
  height = "auto",
  fill = TRUE,
  icon_assistant = NULL,
  enable_cancel = FALSE,
  submit_key = c("enter", "enter+modifier"),
  allow_attachments = FALSE,
  footer = NULL
)
```

## Arguments

- id:

  The ID of the chat element

- ...:

  Extra HTML attributes to include on the chat element

- messages:

  A list of messages to prepopulate the chat with. Each message can be
  one of the following:

  - A string, which is interpreted as markdown and rendered to HTML on
    the client.

    - To prevent interpreting as markdown, mark the string as
      [`htmltools::HTML()`](https://rstudio.github.io/htmltools/reference/HTML.html).

  - A UI element.

    - This includes
      [`htmltools::tagList()`](https://rstudio.github.io/htmltools/reference/tagList.html),
      which take UI elements (including strings) as children. In this
      case, strings are still interpreted as markdown as long as they're
      not inside HTML.

  - A named list of `content` and `role`. The `content` can contain
    content as described above, and the `role` can be "assistant" or
    "user".

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
  If `None`, a default robot icon is used.

- enable_cancel:

  If `TRUE`, show a stop button during streaming that allows the user to
  cancel the in-progress response. When using
  [`chat_mod_server()`](https://posit-dev.github.io/shinychat/r/dev/reference/chat_app.md),
  cancellation is wired up automatically. For manual usage with
  `chat_ui()`, observe `input$<id>_cancel` to handle cancellation (e.g.,
  by calling `ctrl$cancel()` on an ellmer `stream_controller()`).
  Defaults to `FALSE`.

- submit_key:

  Controls which key combination submits the chat message. `"enter"`
  (the default): Enter submits, Shift+Enter adds a newline.
  `"enter+modifier"`: Ctrl+Enter (Cmd+Enter on Mac) submits, plain Enter
  adds a newline.

- allow_attachments:

  Controls the file-attachment affordance (an attach button, plus
  clipboard paste and drag-and-drop) in the chat input. Pass `TRUE` to
  accept all supported types (PNG, JPEG, GIF, WebP, PDF, and common
  text/code files such as Markdown, plain text, CSV, JSON, and source
  files), `FALSE` to disable, or a character vector of MIME types to
  restrict what is accepted (each must be one of the supported types).

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

- footer:

  Optional HTML content to display below the chat input. This can be any
  HTML content (tags, tag lists, or character strings). Useful for
  adding disclaimers, attribution, or other information. The footer text
  is styled slightly smaller and lighter than body text by default.
  Customize with CSS properties `--shiny-chat-footer-font-size` and
  `--shiny-chat-footer-color` on the chat container or footer element.

## Value

A Shiny tag object, suitable for inclusion in a Shiny UI

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
[`chat_mod_server()`](https://posit-dev.github.io/shinychat/r/dev/reference/chat_app.md),
you can access the `greeting_dismissed` reactive from the returned
module value instead of the raw namespaced input string.

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
    chat_append("chat", stream)
  })
}

shinyApp(ui, server)
}
```
