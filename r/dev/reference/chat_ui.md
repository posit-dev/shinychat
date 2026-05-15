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
  placeholder = "Enter a message...",
  width = "min(680px, 100%)",
  height = "auto",
  fill = TRUE,
  icon_assistant = NULL,
  enable_cancel = FALSE
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

## Value

A Shiny tag object, suitable for inclusion in a Shiny UI

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
