test_that("on_save callback fires and values are stored", {
  skip_if_not_installed("shiny")
  store <- InMemoryConversationStore$new()
  client <- .make_test_client()
  captured <- NULL

  ctrl <- .make_test_controller(client, history_options(store = store))
  ctrl$add_save_callback(function(values) {
    values$flag <- TRUE
    captured <<- values
    values
  })
  ctrl$partition <- conversation_partition("test", "alice")

  user_turn <- list(
    class = "ellmer::UserTurn",
    version = 1,
    props = list(
      contents = list(
        list(
          class = "ellmer::ContentText",
          version = 1,
          props = list(text = "Hi")
        )
      )
    )
  )
  asst_turn <- list(
    class = "ellmer::AssistantTurn",
    version = 1,
    props = list(
      contents = list(
        list(
          class = "ellmer::ContentText",
          version = 1,
          props = list(text = "Hello")
        )
      )
    )
  )
  ctrl$on_response(list(user_turn, asst_turn))

  expect_true(!is.null(captured))
  expect_true(isTRUE(ctrl$record$values$flag))
})

test_that("on_restore callback fires on switch", {
  skip_if_not_installed("shiny")
  store <- InMemoryConversationStore$new()
  client <- .make_test_client()
  restored <- NULL

  ctrl <- .make_test_controller(client, history_options(store = store))
  ctrl$add_restore_callback(function(values) {
    restored <<- values
  })
  ctrl$partition <- conversation_partition("test", "alice")

  user_turn <- list(
    class = "ellmer::UserTurn",
    version = 1,
    props = list(
      contents = list(
        list(
          class = "ellmer::ContentText",
          version = 1,
          props = list(text = "Hi")
        )
      )
    )
  )
  asst_turn <- list(
    class = "ellmer::AssistantTurn",
    version = 1,
    props = list(
      contents = list(
        list(
          class = "ellmer::ContentText",
          version = 1,
          props = list(text = "Hello")
        )
      )
    )
  )
  ctrl$on_response(list(user_turn, asst_turn))
  record_id <- ctrl$record$id

  ctrl$new_chat()

  partition <- conversation_partition("test", "alice")
  record <- store$get(partition, record_id)
  record$values <- list(x = 42)
  store$put(partition, record)

  ctrl$switch_to(record_id)
  expect_equal(restored$x, 42)
})

test_that("on_restore does NOT fire on new_chat by default", {
  skip_if_not_installed("shiny")
  store <- InMemoryConversationStore$new()
  client <- .make_test_client()
  restored <- NULL

  ctrl <- .make_test_controller(client, history_options(store = store))
  ctrl$add_restore_callback(function(values) {
    restored <<- values
  })
  ctrl$partition <- conversation_partition("test", "alice")

  user_turn <- list(
    class = "ellmer::UserTurn",
    version = 1,
    props = list(
      contents = list(
        list(
          class = "ellmer::ContentText",
          version = 1,
          props = list(text = "Hi")
        )
      )
    )
  )
  asst_turn <- list(
    class = "ellmer::AssistantTurn",
    version = 1,
    props = list(
      contents = list(
        list(
          class = "ellmer::ContentText",
          version = 1,
          props = list(text = "Hello")
        )
      )
    )
  )
  ctrl$on_response(list(user_turn, asst_turn))
  ctrl$new_chat()

  expect_null(restored)
})

test_that("on_response with no new turns does not overwrite saved values", {
  skip_if_not_installed("shiny")
  store <- InMemoryConversationStore$new()
  client <- .make_test_client()
  accent <- "info"

  ctrl <- .make_test_controller(
    client,
    history_options(store = store, title = NULL)
  )
  ctrl$add_save_callback(function(values) {
    values$accent <- accent
    values
  })
  ctrl$partition <- conversation_partition("test", "alice")

  user_turn <- list(
    class = "ellmer::UserTurn",
    version = 1,
    props = list(
      contents = list(
        list(
          class = "ellmer::ContentText",
          version = 1,
          props = list(text = "Hi")
        )
      )
    )
  )
  asst_turn <- list(
    class = "ellmer::AssistantTurn",
    version = 1,
    props = list(
      contents = list(
        list(
          class = "ellmer::ContentText",
          version = 1,
          props = list(text = "Hello")
        )
      )
    )
  )

  ctrl$on_response(list(user_turn, asst_turn))
  expect_equal(ctrl$record$values$accent, "info")

  accent <- "danger"
  ctrl$on_response(list(user_turn, asst_turn))
  expect_equal(ctrl$record$values$accent, "info")
})

test_that("greeting session state is not wired into conversation record values", {
  skip_if_not_installed("shiny")
  store <- InMemoryConversationStore$new()
  client <- .make_test_client()
  sess <- shiny::MockShinySession$new()
  ctrl <- HistoryController$new(
    chat_id = "test",
    client = client,
    options = history_options(store = store),
    session = sess
  )

  set_session_greeting_state(
    sess,
    "test",
    new_greeting_snapshot(
      content = "Hello",
      content_type = "markdown",
      options = list(persistent = FALSE)
    )
  )
  ctrl$partition <- conversation_partition("test", "alice")

  user_turn <- list(
    class = "ellmer::UserTurn",
    version = 1,
    props = list(
      contents = list(
        list(
          class = "ellmer::ContentText",
          version = 1,
          props = list(text = "Hi")
        )
      )
    )
  )
  asst_turn <- list(
    class = "ellmer::AssistantTurn",
    version = 1,
    props = list(
      contents = list(
        list(
          class = "ellmer::ContentText",
          version = 1,
          props = list(text = "Hello")
        )
      )
    )
  )
  ctrl$on_response(list(user_turn, asst_turn))

  expect_false("greeting" %in% names(ctrl$record$values %||% list()))
  # The greeting snapshot itself is untouched by history save/restore.
  expect_equal(
    get_session_greeting_state(sess, "test")$content,
    "Hello"
  )
})

test_that("HistoryController$save returns FALSE without a record or partition", {
  store <- InMemoryConversationStore$new()
  ctrl <- .make_test_controller(
    .make_test_client(),
    history_options(store = store, title = NULL)
  )

  expect_identical(ctrl$save(), FALSE)

  ctrl$record <- new_conversation_record("Saved conversation")

  expect_identical(ctrl$save(), FALSE)
})

test_that("HistoryController$save_current reports whether it saved", {
  store <- InMemoryConversationStore$new()
  ctrl <- .make_test_controller(
    .make_test_client(),
    history_options(store = store, title = NULL)
  )

  expect_identical(ctrl$save_current(), FALSE)

  ctrl$partition <- conversation_partition("test", "alice")
  ctrl$record <- new_conversation_record("Saved conversation")

  expect_identical(ctrl$save_current(), TRUE)
})

test_that("HistoryController$save persists app state before history updates", {
  store <- InMemoryConversationStore$new()
  client <- .make_test_client()
  session <- shiny::MockShinySession$new()
  ctrl <- HistoryController$new(
    chat_id = "test",
    client = client,
    options = history_options(store = store, title = NULL),
    session = session
  )
  ctrl$partition <- conversation_partition("test", "alice")
  ctrl$record <- new_conversation_record("Saved conversation")

  events <- character()
  session$sendCustomMessage <- function(type, message) {
    if (identical(message$action$type, "history_update")) {
      events <<- c(events, "history")
    }
  }
  ctrl$add_save_callback(function(values) {
    events <<- c(events, "save")
    values$flag <- TRUE
    values
  })
  ctrl$on_response_saved <- function(record) {
    events <<- c(events, "bookmark")
  }

  expect_identical(ctrl$save(), TRUE)
  expect_true(isTRUE(ctrl$record$values$flag))
  expect_equal(events, c("save", "bookmark", "history"))
  expect_equal(
    store$get(ctrl$partition, ctrl$record$id)$values$flag,
    TRUE
  )
})

test_that("HistoryController$save preserves response count after on_response", {
  store <- InMemoryConversationStore$new()
  ctrl <- .make_test_controller(
    .make_test_client(),
    history_options(store = store, title = NULL)
  )
  ctrl$partition <- conversation_partition("test", "alice")

  save_count <- 0L
  ctrl$add_save_callback(function(values) {
    save_count <<- save_count + 1L
    values$save_count <- save_count
    values
  })

  ctrl$on_response(list())
  response_count <- ctrl$record$response_count

  expect_identical(ctrl$save(), TRUE)
  expect_identical(ctrl$record$response_count, response_count)
  expect_identical(ctrl$record$values$save_count, 2L)
})

test_that("HistoryController$save propagates store write errors", {
  FailingStore <- R6::R6Class(
    "FailingStore",
    inherit = ConversationStore,
    public = list(
      list = function(partition) list(),
      get = function(partition, id) NULL,
      put = function(partition, record) rlang::abort("disk full"),
      delete = function(partition, id) invisible(NULL)
    )
  )

  ctrl <- .make_test_controller(
    .make_test_client(),
    history_options(store = FailingStore$new(), title = NULL)
  )
  ctrl$partition <- conversation_partition("test", "alice")
  ctrl$record <- new_conversation_record("Saved conversation")

  expect_error(ctrl$save(), "disk full")
})
