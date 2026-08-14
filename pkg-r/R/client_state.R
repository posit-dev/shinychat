client_get_state <- new_generic("client_get_state", "client")

client_set_state <- new_generic("client_get_state", "client")

client_set_ui <- new_generic(
  "client_set_ui",
  "client",
  function(client, ..., id) {
    S7_dispatch()
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
# state$values. Versioned like client_get_state(): bookmark URLs outlive the
# shinychat that wrote them, so a later format change needs a way to say "this
# isn't mine" rather than handing an unreplayable payload to restore.
UI_SNAPSHOT_VERSION <- 1L

encode_ui_snapshot <- function(messages) {
  if (is.null(messages) || length(messages) == 0) {
    return(NULL)
  }
  list(
    version = UI_SNAPSHOT_VERSION,
    state = gzip_b64_encode(messages)
  )
}

# Returns NULL for anything we can't confidently replay, so callers fall through
# to the turn-derived UI documented in ?chat_restore rather than aborting the
# whole onRestore handler. Warns on the way, since a silent downgrade from
# faithful restore to re-derived UI is otherwise undiagnosable.
decode_ui_snapshot <- function(snapshot) {
  if (is.null(snapshot)) {
    return(NULL)
  }
  # `==` rather than identical(), matching client_set_state(): a version can
  # come back as a double if the store round-trips through JSON.
  if (!is.list(snapshot) || !isTRUE(snapshot$version == UI_SNAPSHOT_VERSION)) {
    rlang::warn(
      "Saved chat UI snapshot is not in a format this shinychat can read; restoring the chat UI from the client's turns instead."
    )
    return(NULL)
  }
  tryCatch(
    gzip_b64_decode(snapshot$state),
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
}

# Render restored chat UI: replay the browser's stored message snapshot when we
# have one (faithful to what the user saw, incl. display-only transforms),
# otherwise re-derive the UI from the client's turns as before.
#
# Checked before replaying anything, not caught mid-loop: restore_history_message()
# sends each message to the client as it's called, so an error partway through
# can't be undone by falling back -- the client would end up with the first N
# snapshot messages *and* the full turn-derived replay stacked on top. A snapshot
# that's the wrong version is already routed to the fallback by decode_ui_snapshot();
# this catches a snapshot that decodes fine (right version, valid JSON) but whose
# per-message shape doesn't hold up -- e.g. bit-level corruption that survives
# gzip/base64/serializeJSON round-tripping intact.
restore_chat_ui <- function(client, id, ui_snapshot, session) {
  if (!is.null(ui_snapshot) && length(ui_snapshot) > 0) {
    if (!all(vapply(ui_snapshot, is_replayable_ui_message, logical(1)))) {
      rlang::warn(
        "Saved chat UI snapshot has an unreplayable message; restoring the chat UI from the client's turns instead."
      )
    } else {
      for (message in ui_snapshot) {
        restore_history_message(id, message, session = session)
      }
      return(invisible())
    }
  }
  client_set_ui(client, id = id)
  invisible()
}

is_replayable_ui_message <- function(message) {
  is.list(message) &&
    is_string(message$role) &&
    message$role %in% c("user", "assistant") &&
    is.list(message$segments) &&
    all(vapply(message$segments, is_replayable_ui_segment, logical(1)))
}

is_replayable_ui_segment <- function(segment) {
  is.list(segment) &&
    is_string(segment$content) &&
    is_string(segment$content_type) &&
    segment$content_type %in% c("markdown", "html", "text", "thinking")
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
