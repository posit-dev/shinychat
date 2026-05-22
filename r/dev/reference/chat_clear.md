# Clear all messages from a chat control

Removes all messages from the chat UI. Set `greeting = TRUE` to also
clear the greeting, which re-triggers `greeting_requested` (see the
**Greeting** section in
[`chat_ui()`](https://posit-dev.github.io/shinychat/r/dev/reference/chat_ui.md)).

## Usage

``` r
chat_clear(id, greeting = FALSE, session = getDefaultReactiveDomain())
```

## Arguments

- id:

  The ID of the chat element

- greeting:

  If `TRUE`, also clears the greeting. When the greeting is cleared,
  `greeting_requested` will fire again (if the chat is visible),
  allowing the server to generate a new greeting.

- session:

  The Shiny session object

## Examples

``` r
if (FALSE) { # interactive()

library(shiny)
library(bslib)

ui <- page_fillable(
  chat_ui("chat", fill = TRUE),
  actionButton("clear", "Clear chat")
)

server <- function(input, output, session) {
  observeEvent(input$clear, {
    chat_clear("chat")
  })

  observeEvent(input$chat_user_input, {
    response <- paste0("You said: ", input$chat_user_input)
    chat_append("chat", response)
  })
}

shinyApp(ui, server)
}
if (FALSE) { # interactive()

library(shiny)
library(bslib)
library(shinychat)

# Regenerate greeting on clear
ui <- page_fillable(
  chat_ui("chat"),
  actionButton("new_chat", "New chat")
)

server <- function(input, output, session) {
  observeEvent(input$chat_greeting_requested, {
    chat_set_greeting("chat", "## Welcome!\n\nHow can I help?")
  })

  observeEvent(input$new_chat, {
    # Clearing with greeting = TRUE triggers greeting_requested again
    chat_clear("chat", greeting = TRUE)
  })

  observeEvent(input$chat_user_input, {
    chat_append("chat", paste0("You said: ", input$chat_user_input))
  })
}

shinyApp(ui, server)
}
```
