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
