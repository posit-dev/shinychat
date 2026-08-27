# Reproduction app for https://github.com/posit-dev/shinychat/issues/336
#
# A slash-command handler that streams its response from an async generator.
# The generator suspends before its first yield, so `chat_append()` opens the
# streaming message on the client (`chunk_start`) and then returns control
# before any content arrives -- at which point chat_server()'s slash-command
# dispatcher unconditionally sends `remove_loading`, force-finalizing the
# still-empty streaming message and dropping every chunk that arrives later.

library(shiny)
library(bslib)
library(coro)
library(shinychat)

response_text <- "Why did the chicken cross the road? To get to the other side!"

make_fake_client <- function() {
  stored_turns <- list()
  client <- list(
    get_turns = function() stored_turns,
    set_turns = function(value) {
      stored_turns <<- value
      invisible(client)
    },
    get_tools = function() list(),
    clone = function() make_fake_client()
  )
  class(client) <- c("Chat", "R6")
  client
}

ui <- page_fillable(
  chat_ui("chat", fill = TRUE, placeholder = "Type / for commands")
)

server <- function(input, output, session) {
  chat <- chat_server("chat", client = make_fake_client(), history = FALSE)

  # Control: a synchronous response completes within the handler invocation,
  # so no streaming message is still open when the dispatcher sends
  # `remove_loading`.
  chat$slash_command(
    "worksync",
    "Do some work synchronously",
    function(content) {
      chat_append("chat", response_text)
    }
  )

  chat$slash_command("work", "Do some work", function(content) {
    stream <- async_generator(function() {
      # Suspend before the first yield so the streaming message is open on the
      # client while this handler has already returned.
      await(async_sleep(0.5))
      for (chunk in strsplit(response_text, "", fixed = TRUE)[[1]]) {
        yield(chunk)
        await(async_sleep(0.01))
      }
    })()

    chat_append("chat", stream)
  })
}

shinyApp(ui, server)
