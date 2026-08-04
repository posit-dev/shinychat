test_that("encode/decode UI snapshot round-trips a simple message", {
  messages <- list(
    list(
      role = "user",
      segments = list(list(content = "hi", content_type = "markdown"))
    )
  )
  encoded <- encode_ui_snapshot(messages)
  expect_type(encoded, "character")
  expect_length(encoded, 1L)
  expect_identical(decode_ui_snapshot(encoded), messages)
})

test_that("encode/decode UI snapshot preserves htmlDeps and attachments", {
  messages <- list(
    list(
      role = "assistant",
      segments = list(
        list(content = "**hi** (displayed)", content_type = "html")
      ),
      htmlDeps = list(
        list(name = "widget", version = "1.0", src = list(href = "w"))
      ),
      attachments = list(
        list(content_type = "image/png", url = "data:...", filename = "a.png")
      )
    )
  )
  expect_identical(decode_ui_snapshot(encode_ui_snapshot(messages)), messages)
})

test_that("encode returns NULL for empty input; decode guards non-values", {
  expect_null(encode_ui_snapshot(list()))
  expect_null(encode_ui_snapshot(NULL))
  expect_null(decode_ui_snapshot(NULL))
  expect_null(decode_ui_snapshot(""))
  expect_null(decode_ui_snapshot(NA_character_))
})

test_that("decode_ui_snapshot returns NULL (not an error) for corrupted input", {
  expect_null(decode_ui_snapshot("not valid base64/gzip"))
  expect_null(
    decode_ui_snapshot(base64enc::base64encode(charToRaw("not gzip")))
  )
})

test_that("restore_chat_ui replays the stored snapshot faithfully", {
  captured <- list()
  local_mocked_bindings(
    send_chat_action = function(id, action, html_deps = NULL, session) {
      captured[[length(captured) + 1]] <<- action
      invisible()
    }
  )
  session <- shiny::MockShinySession$new()
  snapshot <- list(
    list(
      role = "user",
      segments = list(list(content = "hi", content_type = "markdown"))
    ),
    list(
      role = "assistant",
      segments = list(
        list(content = "hello (displayed)", content_type = "markdown")
      )
    )
  )

  restore_chat_ui(
    client = NULL,
    id = "chat",
    ui_snapshot = snapshot,
    session = session
  )

  expect_length(captured, 2L)
  expect_equal(captured[[1]]$message$role, "user")
  expect_equal(captured[[2]]$message$role, "assistant")
  expect_equal(captured[[2]]$message$segments[[1]]$content, "hello (displayed)")
})

test_that("restore_chat_ui falls back to client turns when no snapshot", {
  replay_calls <- 0L
  fallback_calls <- 0L
  local_mocked_bindings(
    restore_history_message = function(chat_id, message, session) {
      replay_calls <<- replay_calls + 1L
    },
    client_set_ui = function(client, ..., id) {
      fallback_calls <<- fallback_calls + 1L
    }
  )
  session <- shiny::MockShinySession$new()

  restore_chat_ui(
    client = NULL,
    id = "chat",
    ui_snapshot = NULL,
    session = session
  )

  expect_equal(replay_calls, 0L)
  expect_equal(fallback_calls, 1L)
})

test_that("restore_chat_ui falls back to client turns when snapshot is empty list", {
  replay_calls <- 0L
  fallback_calls <- 0L
  local_mocked_bindings(
    restore_history_message = function(chat_id, message, session) {
      replay_calls <<- replay_calls + 1L
    },
    client_set_ui = function(client, ..., id) {
      fallback_calls <<- fallback_calls + 1L
    }
  )
  session <- shiny::MockShinySession$new()

  restore_chat_ui(
    client = NULL,
    id = "chat",
    ui_snapshot = list(),
    session = session
  )

  expect_equal(replay_calls, 0L)
  expect_equal(fallback_calls, 1L)
})

test_that("bookmark save/restore round-trips the displayed UI (server store)", {
  session <- shiny::MockShinySession$new()
  snapshot_in <- list(
    list(
      role = "user",
      segments = list(list(content = "hi", content_type = "markdown"))
    ),
    list(
      role = "assistant",
      segments = list(
        list(content = "hello (displayed)", content_type = "markdown")
      )
    )
  )
  local_mocked_bindings(
    is_server_bookmarkstore = function() TRUE,
    get_reported_messages = function(session, chat_id) snapshot_in
  )

  state <- rlang::env(values = list())
  bookmark_save_ui(state, session, "chat")
  expect_type(state$values[["chat_ui"]], "character")

  captured <- list()
  local_mocked_bindings(
    send_chat_action = function(id, action, html_deps = NULL, session) {
      captured[[length(captured) + 1]] <<- action
      invisible()
    }
  )
  bookmark_restore_ui(state, client = NULL, id = "chat", session = session)

  expect_length(captured, 2L)
  expect_equal(captured[[2]]$message$segments[[1]]$content, "hello (displayed)")
})

test_that("bookmark save skips UI capture when store is not server", {
  session <- shiny::MockShinySession$new()
  local_mocked_bindings(
    is_server_bookmarkstore = function() FALSE,
    get_reported_messages = function(session, chat_id) {
      stop("should not be read when store is not server")
    }
  )
  state <- rlang::env(values = list())
  bookmark_save_ui(state, session, "chat")
  expect_null(state$values[["chat_ui"]])

  fallback_calls <- 0L
  local_mocked_bindings(
    client_set_ui = function(client, ..., id) {
      fallback_calls <<- fallback_calls + 1L
    }
  )
  bookmark_restore_ui(state, client = NULL, id = "chat", session = session)
  expect_equal(fallback_calls, 1L)
})

# --- response-bookmark observer -----------------------------------------

ui_message <- function(role, text) {
  list(
    role = role,
    segments = list(list(content = text, content_type = "markdown"))
  )
}

# Runs `body` inside a testServer that has registered chat_restore(), with
# session$doBookmark() replaced by a counter. `body` receives the session, a
# `bookmarks()` reader for the count, and `cancel()` to tear the registrations
# down. `...` is forwarded to chat_restore().
with_restore_server <- function(body, ...) {
  args <- rlang::list2(...)

  count <- 0L
  cancel_all <- NULL
  session <- shiny::MockShinySession$new()
  session$doBookmark <- function() {
    count <<- count + 1L
    invisible()
  }

  server <- function(input, output, session) {
    cancel_all <<- rlang::exec(
      chat_restore,
      "chat",
      mock_chat_client(),
      !!!args,
      session = session
    )
  }

  shiny::testServer(server, session = session, {
    body(
      session,
      bookmarks = function() count,
      cancel = function() cancel_all()
    )
  })
}

test_that("the browser's startup echo never mints a response bookmark", {
  # A fresh session replays the client's existing turns (or a restored
  # snapshot) into the UI, and the browser echoes back one growing `_messages`
  # snapshot per settled message. None of them are user-triggered responses,
  # and any of them can end in an assistant message.
  with_restore_server(function(session, bookmarks, cancel) {
    session$setInputs(chat_messages = list(ui_message("user", "hi")))
    session$setInputs(
      chat_messages = list(
        ui_message("user", "hi"),
        ui_message("assistant", "hello")
      )
    )
    session$setInputs(
      chat_messages = list(
        ui_message("user", "hi"),
        ui_message("assistant", "hello"),
        ui_message("user", "again"),
        ui_message("assistant", "sure")
      )
    )
    expect_equal(bookmarks(), 0L)
  })
})

test_that("a user-only snapshot does not mint a response bookmark", {
  with_restore_server(
    function(session, bookmarks, cancel) {
      session$setInputs(chat_user_input = "hi")
      session$setInputs(chat_messages = list(ui_message("user", "hi")))
      expect_equal(bookmarks(), 0L)
    },
    bookmark_on_input = FALSE
  )
})

test_that("the first settled assistant reply after a startup replay bookmarks exactly once", {
  # Regression: the response guard used to consume a single-use suppression
  # flag, but the startup echoes returned before reaching it -- leaving the
  # flag set to swallow the first genuine response instead. That miss is
  # invisible unless the post-submit echo coalesces the user and assistant
  # messages into one update, which is exactly what this drives.
  with_restore_server(
    function(session, bookmarks, cancel) {
      session$setInputs(chat_messages = list(ui_message("user", "old")))
      session$setInputs(
        chat_messages = list(
          ui_message("user", "old"),
          ui_message("assistant", "older reply")
        )
      )
      expect_equal(bookmarks(), 0L)

      session$setInputs(chat_user_input = "new")
      session$setInputs(
        chat_messages = list(
          ui_message("user", "old"),
          ui_message("assistant", "older reply"),
          ui_message("user", "new"),
          ui_message("assistant", "new reply")
        )
      )
      expect_equal(bookmarks(), 1L)
    },
    bookmark_on_input = FALSE
  )
})

test_that("with bookmark_on_input, the submit and the reply each bookmark once", {
  with_restore_server(function(session, bookmarks, cancel) {
    session$setInputs(chat_messages = list(ui_message("user", "old")))
    expect_equal(bookmarks(), 0L)

    session$setInputs(chat_user_input = "new")
    expect_equal(bookmarks(), 1L)

    session$setInputs(
      chat_messages = list(
        ui_message("user", "new"),
        ui_message("assistant", "reply")
      )
    )
    expect_equal(bookmarks(), 2L)
  })
})

test_that("a submit co-batched with a settled snapshot still bookmarks the reply", {
  # `_user_input` is a persistent input, so it can land in the same reactive
  # flush as the client's snapshot. Shiny invalidates observers in the order the
  # inputs arrive, and the client queues `_user_input` before the snapshot it
  # triggers, so has_user_submitted is set by the time the response observer
  # runs on that flush.
  with_restore_server(
    function(session, bookmarks, cancel) {
      session$setInputs(chat_messages = list())
      session$setInputs(
        chat_user_input = "hi",
        chat_messages = list(
          ui_message("user", "hi"),
          ui_message("assistant", "hello")
        )
      )
      expect_equal(bookmarks(), 1L)
    },
    bookmark_on_input = FALSE
  )
})

test_that("the cancel callback stops both bookmark observers", {
  with_restore_server(function(session, bookmarks, cancel) {
    session$setInputs(chat_user_input = "hi")
    expect_equal(bookmarks(), 1L)

    cancel()

    session$setInputs(chat_user_input = "again")
    session$setInputs(
      chat_messages = list(
        ui_message("user", "again"),
        ui_message("assistant", "sure")
      )
    )
    expect_equal(bookmarks(), 1L)
  })
})

test_that("bookmark_on_response = FALSE never bookmarks on the echo", {
  with_restore_server(
    function(session, bookmarks, cancel) {
      session$setInputs(chat_user_input = "hi")
      session$setInputs(
        chat_messages = list(
          ui_message("user", "hi"),
          ui_message("assistant", "hello")
        )
      )
      expect_equal(bookmarks(), 0L)
    },
    bookmark_on_response = FALSE,
    bookmark_on_input = FALSE
  )
})

test_that("messages_end_with_assistant detects a settled assistant reply", {
  user_only <- list(list(role = "user", segments = list()))
  ends_assistant <- list(
    list(role = "user", segments = list()),
    list(role = "assistant", segments = list())
  )
  expect_false(messages_end_with_assistant(list()))
  expect_false(messages_end_with_assistant(user_only))
  expect_true(messages_end_with_assistant(ends_assistant))
})
