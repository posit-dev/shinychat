MockProvider <- S7::new_class(
  "MockProvider",
  properties = list(
    name = S7::class_character,
    model = S7::class_character
  )
)

mock_provider <- function() {
  MockProvider(name = "Mock", model = "mock-model")
}

mock_chat_client <- function(turns = list()) {
  stored_turns <- turns
  # An environment, like real R6 clients, so in-place assignments such as
  # `client$conversation_id <- id` are visible to the caller (a list would be
  # copy-on-modify and silently drop them).
  obj <- list2env(
    list(
    conversation_id = NULL,
    get_turns = function() stored_turns,
    set_turns = function(value) {
      stored_turns <<- value
      invisible(obj)
    },
    get_tools = function() list(),
    get_provider = function() mock_provider(),
    get_model = function() "mock-model",
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
    ),
    parent = emptyenv()
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
  client$get_provider <- function() mock_provider()
  client$get_model <- function() "mock-model"
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
