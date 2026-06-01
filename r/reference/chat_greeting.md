# Create a greeting for a chat UI

Creates a greeting object for use with
[`chat_ui()`](https://posit-dev.github.io/shinychat/r/reference/chat_ui.md)
or
[`chat_set_greeting()`](https://posit-dev.github.io/shinychat/r/reference/chat_set_greeting.md).
A greeting is displayed when the chat first loads and is dismissed when
the user sends their first message.

## Usage

``` r
chat_greeting(content, dismissible = TRUE)
```

## Arguments

- content:

  The greeting content. Can be:

  - A string, interpreted as markdown.

  - An
    [`htmltools::HTML()`](https://rstudio.github.io/htmltools/reference/HTML.html)
    object, rendered as raw HTML.

  - An htmltools tag or
    [`htmltools::tagList()`](https://rstudio.github.io/htmltools/reference/tagList.html),
    including Shiny inputs/outputs.

  - A generator or promise (only valid when used with
    [`chat_set_greeting()`](https://posit-dev.github.io/shinychat/r/reference/chat_set_greeting.md)).

- dismissible:

  Whether the greeting is automatically dismissed when the user sends a
  message. Defaults to `TRUE`.

## Value

An S3 object of class `"chat_greeting"`.

## Patterns

**Non-dismissible greeting** (stays visible after the user sends a
message):

    chat_greeting("Please read our [terms of service](https://example.com).", dismissible = FALSE)

**Greeting with suggestion cards** (clickable chips that fill the
input):

    chat_greeting(paste(
      "## Welcome!\n\n",
      "Try one of these:\n\n",
      '<span class="suggestion">Summarize my data</span>\n',
      '<span class="suggestion">Create a plot</span>\n',
      '<span class="suggestion">Explain this code</span>'
    ))

**Greeting with HTML tags** (Shiny inputs/outputs):

    chat_greeting(htmltools::tagList(
      htmltools::h2("Welcome!"),
      shiny::selectInput("model", "Choose a model:", c("gpt-4o", "claude-3"))
    ))

## Examples

``` r
if (FALSE) { # interactive()
library(shiny)
library(bslib)
library(shinychat)

ui <- page_fillable(
  chat_ui(
    "chat",
    greeting = chat_greeting("## Welcome!\n\nHow can I help you today?")
  )
)

server <- function(input, output, session) {
  observeEvent(input$chat_user_input, {
    response <- paste0("You said: ", input$chat_user_input)
    chat_append("chat", response)
  })
}

shinyApp(ui, server)
}
```
