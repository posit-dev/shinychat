test_that("history_options() creates config with max_store_mb", {
  config <- history_options(store = "memory", max_store_mb = 50)
  expect_s3_class(config, "chat_history_config")
  expect_equal(config$max_store_mb, 50)
})

test_that("history_options() defaults include max_store_mb = 100", {
  config <- history_options()
  expect_equal(config$store, "auto")
  expect_null(config$scope)
  expect_equal(config$title, "auto")
  expect_equal(config$max_store_mb, 100)
})

test_that("chat_mod_server() accepts history = TRUE", {
  skip_if_not_installed("ellmer")

  client <- mock_chat_client()

  # This tests that the module server doesn't error on setup
  shiny::testServer(
    chat_mod_server,
    args = list(client = client, history = TRUE),
    {
      expect_true(TRUE)
    }
  )
})

test_that("chat_mod_server() accepts history = FALSE", {
  skip_if_not_installed("ellmer")

  client <- mock_chat_client()

  shiny::testServer(
    chat_mod_server,
    args = list(client = client, history = FALSE),
    {
      expect_true(TRUE)
    }
  )
})

test_that("chat_mod_server() accepts history = history_options() config", {
  skip_if_not_installed("ellmer")

  client <- mock_chat_client()
  config <- history_options(store = "memory", max_store_mb = 10)

  shiny::testServer(
    chat_mod_server,
    args = list(client = client, history = config),
    {
      expect_true(TRUE)
    }
  )
})

test_that("deprecated bookmark_on_input warns", {
  skip_if_not_installed("ellmer")
  client <- mock_chat_client()

  expect_warning(
    shiny::testServer(
      chat_mod_server,
      args = list(client = client, bookmark_on_input = TRUE),
      {
        NULL
      }
    ),
    "deprecated"
  )
})

test_that("deprecated bookmark_on_response warns", {
  skip_if_not_installed("ellmer")
  client <- mock_chat_client()

  expect_warning(
    shiny::testServer(
      chat_mod_server,
      args = list(client = client, bookmark_on_response = TRUE),
      {
        NULL
      }
    ),
    "deprecated"
  )
})

test_that("HistoryController evicts oldest when over max_store_bytes", {
  store <- InMemoryConversationStore$new()

  # Pre-populate store with old conversations
  old1 <- new_conversation_record("old one")
  old2 <- new_conversation_record("old two")
  store$put("user1", old1)
  store$put("user1", old2)

  client <- mock_chat_client()
  controller <- HistoryController$new(
    chat_id = "test",
    client = client,
    options = history_options(store = store, max_store_mb = 1e-6, title = NULL),
    session = shiny::MockShinySession$new()
  )
  controller$scope <- "user1"

  # Trigger on_response with empty turns (saves a new record, then evicts old ones)
  controller$on_response(list())

  metas <- store$list("user1")
  ids <- vapply(metas, `[[`, character(1L), "id")

  # Both pre-existing conversations should be evicted; new active one preserved
  expect_false(old1$id %in% ids)
  expect_false(old2$id %in% ids)
  expect_true(controller$record$id %in% ids)
})

test_that("HistoryController does not evict when no limit set", {
  store <- InMemoryConversationStore$new()
  old <- new_conversation_record("old")
  store$put("user1", old)

  client <- mock_chat_client()
  controller <- HistoryController$new(
    chat_id = "test",
    client = client,
    options = history_options(store = store, max_store_mb = NULL, title = NULL),
    session = shiny::MockShinySession$new()
  )
  controller$scope <- "user1"

  controller$on_response(list())

  expect_length(store$list("user1"), 2L) # old + new
})

test_that("HistoryController evict_one removes the record from the store", {
  store <- InMemoryConversationStore$new()
  rec <- new_conversation_record("to evict")
  store$put("user1", rec)

  client <- mock_chat_client()
  controller <- HistoryController$new(
    chat_id = "test",
    client = client,
    options = history_options(store = store, max_store_mb = NULL, title = NULL),
    session = shiny::MockShinySession$new()
  )
  controller$scope <- "user1"

  controller$.__enclos_env__$private$evict_one(rec$id)

  expect_null(store$get("user1", rec$id))
})
