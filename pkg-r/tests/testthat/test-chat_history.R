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
        contents = list(list(
          class = "ellmer::ContentText",
          version = 1,
          props = list(text = user_text)
        ))
      )
    ),
    list(
      class = "ellmer::AssistantTurn",
      version = 1,
      props = list(
        contents = list(list(
          class = "ellmer::ContentText",
          version = 1,
          props = list(text = asst_text)
        ))
      )
    )
  )
}

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
