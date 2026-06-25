mock_chat_client <- function(turns = list()) {
  stored_turns <- turns
  obj <- list(
    get_turns = function() stored_turns,
    set_turns = function(value) {
      stored_turns <<- value
      invisible(obj)
    },
    get_tools = function() list(),
    clone = function() mock_chat_client(stored_turns),
    set_system_prompt = function(prompt) invisible(NULL),
    set_tools = function(tools) invisible(NULL),
    last_turn = function() {
      if (length(stored_turns) > 0) {
        stored_turns[[length(stored_turns)]]
      } else {
        NULL
      }
    }
  )
  class(obj) <- c("Chat", "R6")
  obj
}

.make_test_client <- function() {
  client <- new.env(parent = emptyenv())
  class(client) <- "Chat"
  turns <- list()
  client$get_turns <- function() turns
  client$set_turns <- function(t) {
    turns <<- t
  }
  client$get_system_prompt <- function() NULL
  client$set_system_prompt <- function(p) invisible(NULL)
  client$get_tools <- function() list()
  client$set_tools <- function(t) invisible(NULL)
  client
}

.make_test_controller <- function(client, cfg = history_options()) {
  HistoryController$new(
    chat_id = "test",
    client = client,
    options = cfg,
    session = shiny::MockShinySession$new()
  )
}
