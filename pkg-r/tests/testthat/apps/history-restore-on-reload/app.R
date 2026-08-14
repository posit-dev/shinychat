library(shiny)
library(bslib)
library(shinychat)
library(ellmer)

setClass(
  "HistoryTestProvider",
  representation(name = "character", model = "character")
)

make_echo_client <- function() {
  stored_turns <- list()
  client <- list(
    get_turns = function() stored_turns,
    set_turns = function(value) {
      stored_turns <<- value
      invisible(client)
    },
    get_tools = function() list(),
    get_provider = function() {
      methods::new(
        "HistoryTestProvider",
        name = "Echo",
        model = "echo-test"
      )
    },
    get_model = function() "echo-test",
    clone = function() make_echo_client()
  )
  class(client) <- c("Chat", "R6")
  client
}

record_exchange <- function(client, user_text, assistant_text) {
  turns <- c(
    client$get_turns(),
    list(
      UserTurn(contents = list(ContentText(user_text))),
      AssistantTurn(
        contents = list(ContentText(assistant_text)),
        json = list(1, "two")
      )
    )
  )
  client$set_turns(turns)
}

ui <- page_fillable(
  chat_ui("chat", fill = TRUE, placeholder = "Type a message")
)

server <- function(input, output, session) {
  client <- make_echo_client()
  store <- FileConversationStore$new(
    dir = Sys.getenv("SHINYCHAT_HISTORY_TEST_DIR")
  )

  chat_enable_history(
    "chat",
    client,
    options = history_options(
      store = store,
      scope = "playwright-user",
      title = NULL
    )
  )

  observeEvent(input$chat_user_input, {
    user_input <- input$chat_user_input
    user_text <- if (is.list(user_input)) user_input[[1]] else user_input
    assistant_text <- paste0("echo: ", user_text)
    record_exchange(client, user_text, assistant_text)
    chat_append("chat", assistant_text)
  })
}

shinyApp(ui, server)
