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
      type = "gzip",
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
        stream <- coro::generator(function() {
          for (x in msg_turn$content) {
            coro::yield(x)
          }
        })
        chat_append(id, stream(), msg_turn$role)
      } else {
        chat_append(id, msg_turn$content, role = msg_turn$role)
      }
    })
  }

# Serialize the browser-reported message snapshot for storage in a bookmark's
# state$values. Uses the same stable serializeJSON -> gzip -> base64 pipeline as
# client_get_state(); jsonlite::toJSON()/fromJSON() are lossy round-trips.
encode_ui_snapshot <- function(messages) {
  if (is.null(messages) || length(messages) == 0) {
    return(NULL)
  }
  json <- jsonlite::serializeJSON(messages)
  base64enc::base64encode(memCompress(json, "gzip"))
}

decode_ui_snapshot <- function(str) {
  if (
    is.null(str) ||
      !is.character(str) ||
      length(str) != 1 ||
      is.na(str) ||
      !nzchar(str)
  ) {
    return(NULL)
  }
  json <- memDecompress(
    base64enc::base64decode(str),
    type = "gzip",
    asChar = TRUE
  )
  jsonlite::unserializeJSON(json)
}

# Render restored chat UI: replay the browser's stored message snapshot when we
# have one (faithful to what the user saw, incl. display-only transforms),
# otherwise re-derive the UI from the client's turns as before.
restore_chat_ui <- function(client, id, ui_snapshot, session) {
  if (!is.null(ui_snapshot) && length(ui_snapshot) > 0) {
    for (message in ui_snapshot) {
      restore_history_message(id, message, session = session)
    }
    return(invisible())
  }
  client_set_ui(client, id = id)
  invisible()
}

# Used to avoid R CMD check NOTE about unused imports
`_ignore` <- function() {
  base64enc::base64encode
}
