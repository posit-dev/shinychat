client_get_state <- new_generic(
  "client_get_state",
  "client",
  function(client) {
    result <- S7::S7_dispatch()
  }
)

client_set_state <- new_generic(
  "client_get_state",
  "client",
  function(client, state) {
    S7::S7_dispatch()
  }
)

client_set_ui <- new_generic(
  "client_set_ui",
  "client",
  function(client, ..., id) {
    S7::S7_dispatch()
  }
)

is_server_bookmarkstore <- function() {
  shiny::getShinyOption("bookmarkStore", "server") == "server"
}
is_url_bookmarkstore <- function() {
  shiny::getShinyOption("bookmarkStore", "url") == "url"
}

method(client_get_state, S7::new_S3_class(c("Chat", "R6"))) <-
  function(client) {
    # if (is_server_bookmarkstore()) {
    #   # Serialize the whole chat client
    #   # However, this is a security leak
    #   return(client)
    # }

    A <<- client$get_turns()

    recorded_turns <- lapply(
      client$get_turns(),
      ellmer::contents_record,
      chat = client
    )

    # Pre-serialize the contents so that when shiny:::toJSON() is called, it is stable.
    # jsonlite::toJSON() is not stable as it is a lossy serialization. In addition, jsonlite::fromJSON() (which shiny:::safeFromJSON() uses) is not stable as it tries to make everything a data.frame.
    #
    # * `jsonlite::serializeJSON()` is a stable transformation
    # * `jsonlite::unserializeJSON()` is a stable transformation

    if (is_url_bookmarkstore()) {
      recorded_turns <- lapply(
        recorded_turns,
        function(turn) {
          turn$props$json <- NULL
          turn
        }
      )
    }

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

    # if (is_server_bookmarkstore()) {
    #   # Restore from the saved client object
    #   # Deserialize the whole chat client
    #   # However, this is a security leak
    #   restored_client <- state
    #   client$set_turns(restored_client$get_turns())
    #   return()
    # }

    state_str <- state$state

    state_json <- memDecompress(
      base64enc::base64decode(state_str),
      asChar = TRUE
    )
    recorded_turns <- jsonlite::unserializeJSON(state_json)

    replayed_turns <- lapply(
      recorded_turns,
      ellmer::contents_replay,
      chat = client
    )

    client$set_turns(replayed_turns)
  }


method(client_set_ui, S7::new_S3_class(c("Chat", "R6"))) <-
  function(client, ..., id) {
    # TODO-barret-future; In shinychat, make this a single/internal custom message call to send all the messages at once (and then scroll)
    str(client$get_turns())
    lapply(client$get_turns(), function(turn) {
      chat_append(
        id,
        # Use `contents_markdown()` as it handles image serialization
        # TODO: Use `contents_shinychat()` from posit-dev/shinychat#52
        ellmer::contents_markdown(turn),
        #  turn_info$contents,
        role = turn@role
      )
    })
  }


# Used to avoid R CMD check NOTE about unused imports
`_ignore` <- function() {
  base64enc::base64encode
}
