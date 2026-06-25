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
  ctrl$scope <- "alice"

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
  ctrl$scope <- "alice"

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

  record <- store$get("alice", record_id)
  record$values <- list(x = 42)
  store$put("alice", record)

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
  ctrl$scope <- "alice"

  user_turn <- list(
    class = "ellmer::UserTurn",
    version = 1,
    props = list(
      contents = list(list(
        class = "ellmer::ContentText",
        version = 1,
        props = list(text = "Hi")
      ))
    )
  )
  asst_turn <- list(
    class = "ellmer::AssistantTurn",
    version = 1,
    props = list(
      contents = list(list(
        class = "ellmer::ContentText",
        version = 1,
        props = list(text = "Hello")
      ))
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
  ctrl$scope <- "alice"

  user_turn <- list(
    class = "ellmer::UserTurn",
    version = 1,
    props = list(
      contents = list(list(
        class = "ellmer::ContentText",
        version = 1,
        props = list(text = "Hi")
      ))
    )
  )
  asst_turn <- list(
    class = "ellmer::AssistantTurn",
    version = 1,
    props = list(
      contents = list(list(
        class = "ellmer::ContentText",
        version = 1,
        props = list(text = "Hello")
      ))
    )
  )

  ctrl$on_response(list(user_turn, asst_turn))
  expect_equal(ctrl$record$values$accent, "info")

  accent <- "danger"
  ctrl$on_response(list(user_turn, asst_turn))
  expect_equal(ctrl$record$values$accent, "info")
})
