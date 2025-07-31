client_get_state <- new_generic("client_get_state", "client")

client_set_state <- new_generic("client_get_state", "client")

client_set_ui <- new_generic(
  "client_set_ui",
  "client",
  function(client, ..., id) {
    S7::S7_dispatch()
  }
)

is_server_bookmarkstore <- function() {
  shiny::getShinyOption("bookmarkStore", "") == "server"
}
is_url_bookmarkstore <- function() {
  shiny::getShinyOption("bookmarkStore", "") == "url"
}

method(client_get_state, S7::new_S3_class(c("Chat", "R6"))) <-
  function(client) {
    # Do not record the client object itself. This would be a security leak.
    # Instead, save only the `turns` information
    recorded_turns <- lapply(
      client$get_turns(),
      ellmer::contents_record
    )

    if (is_url_bookmarkstore()) {
      recorded_turns <- lapply(
        recorded_turns,
        function(turn) {
          turn$props$json <- NULL
          turn
        }
      )
    }

    # Pre-serialize the contents so that when shiny:::toJSON() is called, it is stable.
    # jsonlite::toJSON() is not stable as it is a lossy serialization. In addition, jsonlite::fromJSON() (which shiny:::safeFromJSON() uses) is not stable as it tries to make everything a data.frame.
    #
    # * `jsonlite::serializeJSON()` is a stable transformation
    # * `jsonlite::unserializeJSON()` is a stable transformation
    state_json <- jsonlite::serializeJSON(recorded_turns)
    state_str <- base64enc::base64encode(memCompress(state_json, "gzip"))

    list(
      version = 1,
      state = state_str
    )
  }

method(client_set_state, S7::new_S3_class(c("Chat", "R6"))) <-
  function(client, state) {
    if (!is.list(state)) {
      rlang::abort(
        "Invalid state. Expected a list with a 'version' and 'state' element."
      )
    }
    if (state$version != 1) {
      rlang::abort(
        paste0("Invalid state version. Expected 1, got ", state$version)
      )
    }

    state_str <- state$state

    state_json <- memDecompress(
      base64enc::base64decode(state_str),
      asChar = TRUE
    )
    recorded_turns <- jsonlite::unserializeJSON(state_json)

    replayed_turns <- lapply(
      recorded_turns,
      ellmer::contents_replay,
      tools = client$get_tools()
    )

    client$set_turns(replayed_turns)
  }


method(client_set_ui, S7::new_S3_class(c("Chat", "R6"))) <-
  function(client, ..., id) {
    # TODO-future: Disable bookmarking when restoring. Leverage `tryCatch(finally={})`
    # TODO-barret-future; In shinychat, make this a single/internal custom message call to send all the messages at once (and then scroll)

    msgs <- contents_shinychat(client)
    lapply(msgs, function(msg_turn) {
      is_list <- is.list(msg_turn$content) &&
        !inherits(msg_turn$content, c("shiny.tag", "shiny.taglist"))

      if (is_list) {
        chat_append_message(
          id,
          msg = list(role = msg_turn$role, content = ""),
          operation = "append",
          chunk = "start",
        )

        for (content_part in msg_turn$content) {
          chat_append_message(
            id,
            msg = list(role = msg_turn$role, content = content_part),
            operation = "append",
            chunk = TRUE,
          )
        }

        chat_append_message(
          id,
          msg = list(role = msg_turn$role, content = ""),
          operation = "append",
          chunk = "end",
        )
      } else {
        chat_append(id, msg_turn$content, role = msg_turn$role)
      }
    })
  }


# Used to avoid R CMD check NOTE about unused imports
`_ignore` <- function() {
  base64enc::base64encode
}
