library(shiny)
library(bslib)
library(shinychat)

ui <- page_fillable(
  chat_ui("chat", fill = TRUE)
)

server <- function(input, output, session) {
  # Append a user message from the server on init
  # (same code path as bookmark restoration via client_set_ui)
  observe({
    chat_append("chat", "A user message", role = "user")
    chat_append("chat", "An assistant reply")
  })
}

shinyApp(ui, server)
