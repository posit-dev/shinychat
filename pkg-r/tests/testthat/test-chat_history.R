history_mock_session_with_spy <- function() {
  sess <- shiny::MockShinySession$new()
  spy_env <- new.env(parent = emptyenv())
  spy_env$messages <- list()
  sess$sendCustomMessage <- function(type, msg) {
    spy_env$messages[[length(spy_env$messages) + 1L]] <- list(
      type = type,
      message = msg
    )
  }
  list(session = sess, spy_env = spy_env)
}

history_spy_messages <- function(spy) spy$spy_env$messages

test_that("HistoryController$on_response() creates record on first save", {
  store <- InMemoryConversationStore$new()
  client <- mock_chat_client()
  session <- shiny::MockShinySession$new()

  ctrl <- HistoryController$new(
    chat_id = "chat",
    client = client,
    options = history_options(store = store, title = NULL),
    session = session
  )
  ctrl$scope <- "test-user"

  # Simulate a user turn + assistant turn
  user_turn <- list(
    class = "ellmer::UserTurn",
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
  asst_turn <- list(
    class = "ellmer::AssistantTurn",
    version = 1,
    props = list(
      contents = list(
        list(
          class = "ellmer::ContentText",
          version = 1,
          props = list(text = "Hi there")
        )
      )
    )
  )

  ctrl$on_response(list(user_turn, asst_turn))

  expect_false(is.null(ctrl$record))
  expect_equal(ctrl$record$title, "Hello")
  expect_equal(length(ctrl$record$nodes), 2)
  expect_length(store$list("test-user"), 1)
})

test_that("HistoryController$on_response() extends existing record", {
  store <- InMemoryConversationStore$new()
  client <- mock_chat_client()
  session <- shiny::MockShinySession$new()

  ctrl <- HistoryController$new(
    chat_id = "chat",
    client = client,
    options = history_options(store = store, title = NULL),
    session = session
  )
  ctrl$scope <- "test-user"

  turn1 <- list(
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
  turn2 <- list(
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

  ctrl$on_response(list(turn1, turn2))
  expect_equal(length(ctrl$record$nodes), 2)

  turn3 <- list(
    class = "ellmer::UserTurn",
    version = 1,
    props = list(
      contents = list(
        list(
          class = "ellmer::ContentText",
          version = 1,
          props = list(text = "More")
        )
      )
    )
  )
  turn4 <- list(
    class = "ellmer::AssistantTurn",
    version = 1,
    props = list(
      contents = list(
        list(
          class = "ellmer::ContentText",
          version = 1,
          props = list(text = "Sure")
        )
      )
    )
  )

  ctrl$on_response(list(turn1, turn2, turn3, turn4))
  expect_equal(length(ctrl$record$nodes), 4)
})

test_that("HistoryController$new_chat() resets state", {
  store <- InMemoryConversationStore$new()
  client <- mock_chat_client()
  session <- shiny::MockShinySession$new()

  ctrl <- HistoryController$new(
    chat_id = "chat",
    client = client,
    options = history_options(store = store, title = NULL),
    session = session
  )
  ctrl$scope <- "test-user"

  turn1 <- list(
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
  turn2 <- list(
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
  ctrl$on_response(list(turn1, turn2))

  saved_id <- ctrl$record$id
  ctrl$new_chat()

  expect_null(ctrl$record)
  # Old conversation still in store
  expect_false(is.null(store$get("test-user", saved_id)))
})

test_that("HistoryController$rename() updates title", {
  store <- InMemoryConversationStore$new()
  client <- mock_chat_client()
  session <- shiny::MockShinySession$new()

  ctrl <- HistoryController$new(
    chat_id = "chat",
    client = client,
    options = history_options(store = store, title = NULL),
    session = session
  )
  ctrl$scope <- "test-user"

  turn1 <- list(
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
  turn2 <- list(
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
  ctrl$on_response(list(turn1, turn2))

  ctrl$rename(ctrl$record$id, "Renamed chat")
  expect_equal(ctrl$record$title, "Renamed chat")
  expect_equal(ctrl$record$title_source, "user")
  expect_equal(store$get("test-user", ctrl$record$id)$title, "Renamed chat")
})

test_that("HistoryController$delete() removes conversation", {
  store <- InMemoryConversationStore$new()
  client <- mock_chat_client()
  session <- shiny::MockShinySession$new()

  ctrl <- HistoryController$new(
    chat_id = "chat",
    client = client,
    options = history_options(store = store, title = NULL),
    session = session
  )
  ctrl$scope <- "test-user"

  turn1 <- list(
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
  turn2 <- list(
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
  ctrl$on_response(list(turn1, turn2))
  conv_id <- ctrl$record$id

  ctrl$delete(conv_id)
  expect_null(store$get("test-user", conv_id))
  expect_null(ctrl$record)
})

test_that("HistoryController suppresses saves during replay", {
  store <- InMemoryConversationStore$new()
  client <- mock_chat_client()
  session <- shiny::MockShinySession$new()

  ctrl <- HistoryController$new(
    chat_id = "chat",
    client = client,
    options = history_options(store = store, title = NULL),
    session = session
  )
  ctrl$scope <- "test-user"
  ctrl$is_replaying <- TRUE

  turn1 <- list(
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
  ctrl$on_response(list(turn1))

  expect_null(ctrl$record)
  expect_length(store$list("test-user"), 0)
})

make_turns <- function(user_text = "Hi", asst_text = "Hello") {
  list(
    list(
      class = "ellmer::UserTurn",
      version = 1,
      props = list(
        contents = list(
          list(
            class = "ellmer::ContentText",
            version = 1,
            props = list(text = user_text)
          )
        )
      )
    ),
    list(
      class = "ellmer::AssistantTurn",
      version = 1,
      props = list(
        contents = list(
          list(
            class = "ellmer::ContentText",
            version = 1,
            props = list(text = asst_text)
          )
        )
      )
    )
  )
}

flush_promises <- function(timeout = 2) {
  deadline <- Sys.time() + timeout
  while (Sys.time() < deadline) {
    later::run_now(0.05)
  }
}

test_that("title stays fallback after first response", {
  store <- InMemoryConversationStore$new()
  client <- mock_chat_client()
  session <- shiny::MockShinySession$new()

  ctrl <- HistoryController$new(
    chat_id = "chat",
    client = client,
    options = history_options(
      store = store,
      title = function(recorded_turns) "Generated Title"
    ),
    session = session
  )
  ctrl$scope <- "test-user"

  ctrl$on_response(make_turns("Hi", "Hello"))

  expect_equal(ctrl$record$response_count, 1L)
  expect_null(ctrl$record$title_source)
})

test_that("titling fires after the second response, exactly once", {
  store <- InMemoryConversationStore$new()
  client <- mock_chat_client()
  session <- shiny::MockShinySession$new()

  ctrl <- HistoryController$new(
    chat_id = "chat",
    client = client,
    options = history_options(
      store = store,
      title = function(recorded_turns) "Generated Title"
    ),
    session = session
  )
  ctrl$scope <- "test-user"

  ctrl$on_response(make_turns("Hi", "Hello"))
  turns <- c(make_turns("Hi", "Hello"), make_turns("More", "Sure"))
  ctrl$on_response(turns)

  expect_equal(ctrl$record$response_count, 2L)
  flush_promises()
  expect_equal(ctrl$record$title, "Generated Title")
  expect_equal(ctrl$record$title_source, "llm")
})

test_that("rename between the first and second response blocks auto-titling", {
  store <- InMemoryConversationStore$new()
  client <- mock_chat_client()
  session <- shiny::MockShinySession$new()

  ctrl <- HistoryController$new(
    chat_id = "chat",
    client = client,
    options = history_options(
      store = store,
      title = function(recorded_turns) "Generated Title"
    ),
    session = session
  )
  ctrl$scope <- "test-user"

  ctrl$on_response(make_turns("Hi", "Hello"))
  ctrl$rename(ctrl$record$id, "My Title")

  turns <- c(make_turns("Hi", "Hello"), make_turns("More", "Sure"))
  ctrl$on_response(turns)
  flush_promises()

  expect_equal(ctrl$record$title, "My Title")
  expect_equal(ctrl$record$title_source, "user")
})

test_that("titling fires on the second response across sessions", {
  store <- InMemoryConversationStore$new()
  client <- mock_chat_client()

  ctrl1 <- HistoryController$new(
    chat_id = "chat",
    client = client,
    options = history_options(
      store = store,
      title = function(recorded_turns) "Generated Title"
    ),
    session = shiny::MockShinySession$new()
  )
  ctrl1$scope <- "test-user"
  ctrl1$on_response(make_turns("Hi", "Hello"))
  conv_id <- ctrl1$record$id

  # Simulate a brand-new session: fresh controller, same backing store,
  # loads the persisted (1-response) conversation before continuing it.
  ctrl2 <- HistoryController$new(
    chat_id = "chat",
    client = client,
    options = history_options(
      store = store,
      title = function(recorded_turns) "Generated Title"
    ),
    session = shiny::MockShinySession$new()
  )
  ctrl2$scope <- "test-user"
  ctrl2$record <- store$get("test-user", conv_id)

  turns <- c(make_turns("Hi", "Hello"), make_turns("More", "Sure"))
  ctrl2$on_response(turns)
  flush_promises()

  expect_equal(ctrl2$record$title, "Generated Title")
  expect_equal(ctrl2$record$title_source, "llm")
})

test_that("on_response defaults a missing response_count to 0 before incrementing", {
  store <- InMemoryConversationStore$new()
  client <- mock_chat_client()
  session <- shiny::MockShinySession$new()

  ctrl <- HistoryController$new(
    chat_id = "chat",
    client = client,
    options = history_options(store = store, title = NULL),
    session = session
  )
  ctrl$scope <- "test-user"
  ctrl$on_response(make_turns("Hi", "Hello"))
  ctrl$record$response_count <- NULL # simulate a pre-existing record on disk

  turns <- c(make_turns("Hi", "Hello"), make_turns("More", "Sure"))
  ctrl$on_response(turns)

  expect_equal(ctrl$record$response_count, 1L)
})

test_that("on_response_saved fires on every response", {
  store <- InMemoryConversationStore$new()
  client <- mock_chat_client()
  session <- shiny::MockShinySession$new()

  ctrl <- HistoryController$new(
    chat_id = "chat",
    client = client,
    options = history_options(store = store, title = "fallback"),
    session = session
  )
  ctrl$scope <- "test-user"

  fired_ids <- character(0)
  ctrl$on_response_saved <- function(record) {
    fired_ids <<- c(fired_ids, record$id)
  }

  ctrl$on_response(make_turns("Hello", "Hi"))
  expect_length(fired_ids, 1)

  all_turns <- c(make_turns("Hello", "Hi"), make_turns("More", "Sure"))
  ctrl$on_response(all_turns)
  expect_length(fired_ids, 2)
  expect_equal(fired_ids[[1]], fired_ids[[2]])
})

test_that("on_pre_switch returning TRUE skips the in-session swap", {
  store <- InMemoryConversationStore$new()
  client <- mock_chat_client()
  session <- shiny::MockShinySession$new()

  ctrl <- HistoryController$new(
    chat_id = "chat",
    client = client,
    options = history_options(store = store, title = "fallback"),
    session = session
  )
  ctrl$scope <- "test-user"

  # Create two conversations
  ctrl$on_response(make_turns("A", "B"))
  first_id <- ctrl$record$id

  ctrl$new_chat()
  ctrl$on_response(make_turns("C", "D"))
  second_id <- ctrl$record$id

  pre_switch_targets <- list()
  ctrl$on_pre_switch <- function(target) {
    pre_switch_targets[[length(pre_switch_targets) + 1]] <<- target
    TRUE # signal to skip the swap
  }

  ctrl$switch_to(first_id)

  # Hook fired
  expect_length(pre_switch_targets, 1)
  expect_equal(pre_switch_targets[[1]]$id, first_id)
  # Record was NOT updated because hook returned TRUE
  expect_equal(ctrl$record$id, second_id)
})

test_that("on_pre_switch returning FALSE allows the in-session swap", {
  store <- InMemoryConversationStore$new()
  client <- mock_chat_client()
  session <- shiny::MockShinySession$new()

  ctrl <- HistoryController$new(
    chat_id = "chat",
    client = client,
    options = history_options(store = store, title = "fallback"),
    session = session
  )
  ctrl$scope <- "test-user"

  ctrl$on_response(make_turns("A", "B"))
  first_id <- ctrl$record$id

  ctrl$new_chat()
  ctrl$on_response(make_turns("C", "D"))
  second_id <- ctrl$record$id

  ctrl$on_pre_switch <- function(target) FALSE

  ctrl$switch_to(first_id)

  expect_equal(ctrl$record$id, first_id)
})

test_that("bookmark mode pre-switch emits reload navigation", {
  spy <- history_mock_session_with_spy()
  client <- mock_chat_client()
  store <- InMemoryConversationStore$new()

  old_bookmark_store <- shiny::getShinyOption("bookmarkStore", NULL)
  shiny::shinyOptions(bookmarkStore = "server")
  withr::defer(shiny::shinyOptions(bookmarkStore = old_bookmark_store))

  chat_enable_history(
    "chat",
    client,
    options = history_options(
      store = store,
      scope = "test-user",
      restore_mode = "bookmark",
      title = NULL
    ),
    session = spy$session
  )

  ctrl <- get_session_chat_bookmark_info(spy$session, "chat.history-controller")
  target <- new_conversation_record("target")
  target$bookmark_state_id <- "state123"

  expect_true(ctrl$on_pre_switch(target))

  messages <- history_spy_messages(spy)
  nav <- Filter(
    function(m) {
      identical(m$type, "shinyChatMessage") &&
        identical(m$message$action$type, "history_navigate")
    },
    messages
  )

  expect_length(nav, 1)
  expect_equal(nav[[1]]$message$action$url, "?_state_id_=state123")
  expect_equal(nav[[1]]$message$action$active_id, target$id)
  expect_true(nav[[1]]$message$action$reload)
})

test_that("delete_bookmark_state removes Shiny appDir server bookmark state", {
  old_app_dir <- shiny::getShinyOption("appDir", NULL)
  old_bookmark_save_dir <- shiny::getShinyOption("bookmarkSaveDir", NULL)
  withr::defer(shiny::shinyOptions(appDir = old_app_dir))
  withr::defer(shiny::shinyOptions(bookmarkSaveDir = old_bookmark_save_dir))

  app_dir <- withr::local_tempdir()
  state_dir <- file.path(app_dir, "shiny_bookmarks", "state123")
  dir.create(state_dir, recursive = TRUE)
  writeLines("saved", file.path(state_dir, "input.rds"))

  shiny::shinyOptions(appDir = app_dir)
  shiny::shinyOptions(bookmarkSaveDir = NULL)

  delete_bookmark_state("state123")

  expect_false(dir.exists(state_dir))
})

test_that("on_evict fires before store$delete in evict_one and delete", {
  store <- InMemoryConversationStore$new()
  client <- mock_chat_client()
  session <- shiny::MockShinySession$new()

  ctrl <- HistoryController$new(
    chat_id = "chat",
    client = client,
    options = history_options(store = store, title = "fallback"),
    session = session
  )
  ctrl$scope <- "test-user"

  ctrl$on_response(make_turns("A", "B"))
  conv_id <- ctrl$record$id

  evict_saw_record_in_store <- NULL
  ctrl$on_evict <- function(id) {
    evict_saw_record_in_store <<- !is.null(store$get("test-user", id))
  }

  ctrl$delete(conv_id)

  expect_true(evict_saw_record_in_store)
  expect_null(store$get("test-user", conv_id))
})
