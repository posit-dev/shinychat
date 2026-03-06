# Clear all messages from a chat control

Clear all messages from a chat control

## Usage

``` r
chat_clear(id, session = getDefaultReactiveDomain())
```

## Arguments

- id:

  The ID of the chat element

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
```
