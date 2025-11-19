# Create a chat UI element

Inserts a chat UI element into a Shiny UI, which includes a scrollable
section for displaying chat messages, and an input field for the user to
enter new messages.

To respond to user input, listen for `input$ID_user_input` (for example,
if `id="my_chat"`, user input will be at `input$my_chat_user_input`),
and use
[`chat_append()`](https://posit-dev.github.io/shinychat/r/reference/chat_append.md)
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
  icon_assistant = NULL
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

## Value

A Shiny tag object, suitable for inclusion in a Shiny UI

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
