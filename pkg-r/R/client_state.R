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

    list(
      version = 1,
      state = gzip_b64_encode(recorded_turns)
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

    recorded_turns <- gzip_b64_decode(state$state)

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
# state$values.
encode_ui_snapshot <- function(messages) {
  if (is.null(messages) || length(messages) == 0) {
    return(NULL)
  }
  gzip_b64_encode(messages)
}

# Returns NULL for anything we can't confidently replay, so callers fall through
# to the turn-derived UI documented in ?chat_restore rather than aborting the
# whole onRestore handler. Warns on the way, since a silent downgrade from
# faithful restore to re-derived UI is otherwise undiagnosable.
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
  snapshot <- tryCatch(
    gzip_b64_decode(str),
    error = function(e) {
      rlang::warn(
        c(
          "Saved chat UI snapshot could not be decoded; restoring the chat UI from the client's turns instead.",
          i = conditionMessage(e)
        )
      )
      NULL
    }
  )
  if (is.null(snapshot)) {
    return(NULL)
  }
  if (!is_ui_snapshot(snapshot)) {
    rlang::warn(
      "Saved chat UI snapshot is not a chat transcript; restoring the chat UI from the client's turns instead."
    )
    return(NULL)
  }
  snapshot
}

is_ui_snapshot <- function(x) {
  is.list(x) && is.null(names(x)) && all(vapply(x, is_ui_message, logical(1)))
}

is_ui_message <- function(x) {
  is.list(x) &&
    is_string(x$role) &&
    is.list(x$segments) &&
    is.null(names(x$segments)) &&
    all(vapply(x$segments, is_ui_segment, logical(1))) &&
    (is.null(x$attachments) || is.list(x$attachments)) &&
    (is.null(x$htmlDeps) || is.list(x$htmlDeps))
}

is_ui_segment <- function(x) {
  is.list(x) && is_string(x$content) && is_string(x$content_type)
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

# Shared codec for anything we stash in a bookmark's state$values.
#
# serializeJSON/unserializeJSON rather than toJSON/fromJSON: toJSON() is a lossy
# transformation and fromJSON() (which shiny:::safeFromJSON() uses) coerces
# structures into data.frames, so neither round-trips these objects. Both
# serializeJSON() and unserializeJSON() are stable. gzip keeps the payload small
# enough to live in bookmark state.
gzip_b64_encode <- function(x) {
  base64enc::base64encode(memCompress(jsonlite::serializeJSON(x), "gzip"))
}

# `type = "gzip"` must be explicit: memCompress(x, "gzip") writes RFC 1950
# (zlib) data, and memDecompress's default `type = "unknown"` only detects that
# reliably from R 4.4.0 on. Older R silently falls back to "none" and corrupts
# the payload.
gzip_b64_decode <- function(str) {
  json <- memDecompress(
    base64enc::base64decode(str),
    type = "gzip",
    asChar = TRUE
  )
  jsonlite::unserializeJSON(json)
}
