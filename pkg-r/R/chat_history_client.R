get_turns_recorded <- function(client) {
  lapply(client$get_turns(), ellmer::contents_record)
}

set_turns_recorded <- function(client, recorded_turns) {
  replayed <- lapply(
    recorded_turns,
    ellmer::contents_replay,
    tools = client$get_tools()
  )
  client$set_turns(replayed)
}

get_client_info <- function(client) {
  provider <- client$get_provider()
  list(provider = provider@name, model = provider@model)
}

turn_fallback_markdown <- function(recorded_turn) {
  contents <- recorded_turn$props$contents
  if (!is.list(contents)) {
    return("")
  }

  texts <- vapply(
    contents,
    function(item) {
      if (grepl("ContentText$", item$class %||% "")) {
        item$props$text %||% ""
      } else {
        ""
      }
    },
    character(1)
  )

  paste0(texts, collapse = "")
}
