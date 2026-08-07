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

history_append_message <- function(
  session,
  role,
  content,
  attachments = NULL,
  html_deps = NULL
) {
  get_chat_transcript(session, "chat")$append(
    list(
      role = role,
      segments = list(
        list(content = content, content_type = "markdown")
      ),
      attachments = attachments,
      htmlDeps = html_deps
    )
  )
}

history_record_messages <- function(record) {
  unlist(
    lapply(record_path_node_ids(record), function(node_id) {
      record$nodes[[node_id]]$ui %||% list()
    }),
    recursive = FALSE
  )
}

test_that("HistoryController$on_response() saves a managed transcript once", {
  put_calls <- 0L
  RecordingStore <- R6::R6Class(
    "RecordingStore",
    inherit = InMemoryConversationStore,
    public = list(
      put = function(partition, record) {
        put_calls <<- put_calls + 1L
        super$put(partition, record)
      }
    )
  )
  store <- RecordingStore$new()
  client <- mock_chat_client()
  session <- shiny::MockShinySession$new()
  history_append_message(session, "user", "Hello")
  history_append_message(session, "assistant", "Notice")
  history_append_message(session, "assistant", "Hi there")

  ctrl <- HistoryController$new(
    chat_id = "chat",
    client = client,
    options = history_options(store = store, title = NULL),
    session = session
  )
  ctrl$partition <- conversation_partition("chat", "test-user")

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

  expect_equal(put_calls, 1L)
  expect_equal(ctrl$record$title, "Hello")
  expect_equal(length(ctrl$record$nodes), 2)
  expect_equal(ctrl$record$response_count, 1L)
  expect_equal(ctrl$transcript_offset, 3L)
  expect_equal(
    vapply(
      history_record_messages(ctrl$record),
      function(message) message$segments[[1L]]$content,
      character(1L)
    ),
    c("Hello", "Notice", "Hi there")
  )
  expect_length(store$list(conversation_partition("chat", "test-user")), 1)
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
  ctrl$partition <- conversation_partition("chat", "test-user")

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

test_that("HistoryController retries failed response persistence atomically", {
  attempts <- 0L
  FailingOnceStore <- R6::R6Class(
    "FailingOnceStore",
    inherit = InMemoryConversationStore,
    public = list(
      put = function(partition, record) {
        attempts <<- attempts + 1L
        if (attempts == 1L) {
          rlang::abort("disk full")
        }
        super$put(partition, record)
      }
    )
  )
  store <- FailingOnceStore$new()
  client <- mock_chat_client()
  session <- shiny::MockShinySession$new()
  history_append_message(session, "user", "Hi")

  ctrl <- HistoryController$new(
    chat_id = "chat",
    client = client,
    options = history_options(store = store, title = NULL),
    session = session
  )
  ctrl$partition <- conversation_partition("chat", "test-user")

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

  expect_error(ctrl$on_response(list(turn1)), "disk full", fixed = TRUE)
  expect_null(ctrl$record)
  expect_equal(ctrl$transcript_offset, 0L)

  ctrl$on_response(list(turn1))

  expect_equal(attempts, 2L)
  expect_equal(ctrl$record$response_count, 1L)
  expect_equal(
    history_record_messages(ctrl$record),
    list(
      list(
        role = "user",
        segments = list(list(content = "Hi", content_type = "markdown"))
      )
    )
  )
  expect_equal(ctrl$transcript_offset, 1L)
})

test_that("HistoryController retries failed switch persistence atomically", {
  attempts <- 0L
  failures <- 0L
  ToggleStore <- R6::R6Class(
    "ToggleStore",
    inherit = InMemoryConversationStore,
    public = list(
      put = function(partition, record) {
        attempts <<- attempts + 1L
        if (failures > 0L) {
          failures <<- failures - 1L
          rlang::abort("disk full")
        }
        super$put(partition, record)
      }
    )
  )
  store <- ToggleStore$new()
  client <- mock_chat_client()
  session <- shiny::MockShinySession$new()
  history_append_message(session, "user", "Hi")

  ctrl <- HistoryController$new(
    chat_id = "chat",
    client = client,
    options = history_options(store = store, title = NULL),
    session = session
  )
  ctrl$partition <- conversation_partition("chat", "test-user")
  ctrl$on_response(
    list(
      list(
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
    )
  )

  original_record <- ctrl$record
  original_value <- copy_value(original_record)
  history_append_message(session, "assistant", "Out of band")
  failures <- 1L

  expect_error(ctrl$save_current(), "disk full", fixed = TRUE)
  expect_identical(ctrl$record, original_record)
  expect_identical(ctrl$record, original_value)
  expect_equal(ctrl$transcript_offset, 1L)

  ctrl$save_current()

  expect_equal(attempts, 3L)
  expect_equal(ctrl$record$response_count, 1L)
  expect_equal(
    vapply(
      history_record_messages(ctrl$record),
      function(message) message$segments[[1L]]$content,
      character(1L)
    ),
    c("Hi", "Out of band")
  )
  expect_equal(ctrl$transcript_offset, 2L)
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
  ctrl$partition <- conversation_partition("chat", "test-user")

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
  ctrl$partition <- conversation_partition("chat", "test-user")

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
  ctrl$partition <- conversation_partition("chat", "test-user")

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
  ctrl1$partition <- conversation_partition("chat", "test-user")
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
  ctrl2$partition <- conversation_partition("chat", "test-user")
  ctrl2$record <- store$get(
    conversation_partition("chat", "test-user"),
    conv_id
  )

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
  ctrl$partition <- conversation_partition("chat", "test-user")
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
    options = history_options(store = store, title = NULL),
    session = session
  )
  ctrl$partition <- conversation_partition("chat", "test-user")

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
    options = history_options(store = store, title = NULL),
    session = session
  )
  ctrl$partition <- conversation_partition("chat", "test-user")

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
    options = history_options(store = store, title = NULL),
    session = session
  )
  ctrl$partition <- conversation_partition("chat", "test-user")

  ctrl$on_response(make_turns("A", "B"))
  first_id <- ctrl$record$id

  ctrl$new_chat()
  ctrl$on_response(make_turns("C", "D"))
  second_id <- ctrl$record$id

  ctrl$on_pre_switch <- function(target) FALSE

  ctrl$switch_to(first_id)

  expect_equal(ctrl$record$id, first_id)
})

test_that("switch_to() raises on a nonexistent conversation id", {
  store <- InMemoryConversationStore$new()
  client <- mock_chat_client()
  session <- shiny::MockShinySession$new()

  ctrl <- HistoryController$new(
    chat_id = "chat",
    client = client,
    options = history_options(store = store, title = NULL),
    session = session
  )
  ctrl$partition <- conversation_partition("chat", "test-user")

  expect_error(ctrl$switch_to("does-not-exist"), "Conversation not found")
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

test_that("HistoryController$on_response() attaches transcript messages to nodes", {
  store <- InMemoryConversationStore$new()
  client <- mock_chat_client()
  session <- shiny::MockShinySession$new()
  get_chat_transcript(session, "chat")$replace(
    list(
      list(
        role = "user",
        segments = list(list(content = "Hello", content_type = "markdown"))
      ),
      list(
        role = "assistant",
        segments = list(list(content = "Hi there", content_type = "markdown"))
      )
    )
  )

  ctrl <- HistoryController$new(
    chat_id = "chat",
    client = client,
    options = history_options(store = store, title = NULL),
    session = session
  )
  ctrl$partition <- conversation_partition("chat", "test-user")

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

  expect_equal(ctrl$record$nodes$n_0001$ui[[1]]$segments[[1]]$content, "Hello")
  expect_equal(
    ctrl$record$nodes$n_0002$ui[[1]]$segments[[1]]$content,
    "Hi there"
  )
  expect_equal(ctrl$transcript_offset, 2)
})

test_that("HistoryController$on_response() is idempotent without new state", {
  store <- InMemoryConversationStore$new()
  client <- mock_chat_client()
  session <- shiny::MockShinySession$new()
  get_chat_transcript(session, "chat")$replace(
    list(
      list(
        role = "user",
        segments = list(list(content = "Hello", content_type = "markdown"))
      )
    )
  )

  ctrl <- HistoryController$new(
    chat_id = "chat",
    client = client,
    options = history_options(store = store, title = NULL),
    session = session
  )
  ctrl$partition <- conversation_partition("chat", "test-user")

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
  ctrl$on_response(list(user_turn))
  expect_equal(length(ctrl$record$nodes), 1)

  # Simulate a restore-triggered re-report of the *same* (or shorter/equal)
  # snapshot: on_response() must not touch the record.
  updated_at_before <- ctrl$record$updated_at
  ctrl$on_response(list(user_turn))
  expect_identical(ctrl$record$updated_at, updated_at_before)
})

test_that("HistoryController$replay_ui() replays stored ui verbatim and seeds transcript_offset from the restore count", {
  store <- InMemoryConversationStore$new()
  client <- mock_chat_client()
  session <- shiny::MockShinySession$new()

  ctrl <- HistoryController$new(
    chat_id = "chat",
    client = client,
    options = history_options(store = store, title = NULL),
    session = session
  )
  ctrl$partition <- conversation_partition("chat", "test-user")

  rec <- new_conversation_record("test")
  rec$nodes <- list(
    n_0001 = list(
      parent = NULL,
      children = list(),
      turns = list(
        list(
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
      ),
      ui = list(
        list(
          role = "user",
          segments = list(list(content = "Hello", content_type = "markdown"))
        )
      )
    )
  )
  rec$current_leaf <- "n_0001"

  ctrl$replay_ui(rec)

  expect_equal(ctrl$transcript_offset, 1)
})

test_that("HistoryController$replay_ui() falls back to turn-derived markdown when a node has no stored ui", {
  store <- InMemoryConversationStore$new()
  client <- mock_chat_client()
  session <- shiny::MockShinySession$new()
  spy <- history_mock_session_with_spy()

  ctrl <- HistoryController$new(
    chat_id = "chat",
    client = client,
    options = history_options(store = store, title = NULL),
    session = spy$session
  )
  ctrl$partition <- conversation_partition("chat", "test-user")

  rec <- new_conversation_record("test")
  rec$nodes <- list(
    n_0001 = list(
      parent = NULL,
      children = list(),
      turns = list(
        list(
          class = "ellmer::AssistantTurn",
          version = 1,
          props = list(
            contents = list(
              list(
                class = "ellmer::ContentText",
                version = 1,
                props = list(text = "fallback text")
              )
            )
          )
        )
      ),
      ui = NULL
    )
  )
  rec$current_leaf <- "n_0001"

  ctrl$replay_ui(rec)

  sent <- history_spy_messages(spy)
  message_actions <- Filter(
    function(m) identical(m$message$action$type, "message"),
    sent
  )
  expect_length(message_actions, 1)
  expect_equal(
    message_actions[[1]]$message$action$message$segments[[1]]$content,
    "fallback text"
  )
  expect_equal(ctrl$transcript_offset, 1)
})

test_that("an out-of-band message survives a conversation switch and restore", {
  store <- InMemoryConversationStore$new()
  client <- mock_chat_client()
  session <- shiny::MockShinySession$new()
  get_chat_transcript(session, "chat")$replace(
    list(
      list(
        role = "user",
        segments = list(list(content = "hi", content_type = "markdown"))
      ),
      list(
        role = "assistant",
        segments = list(list(content = "hello", content_type = "markdown"))
      ),
      list(
        role = "assistant",
        segments = list(
          list(content = "Note: rate limit reset.", content_type = "markdown")
        )
      )
    )
  )

  ctrl <- HistoryController$new(
    chat_id = "chat",
    client = client,
    options = history_options(store = store, title = NULL),
    session = session
  )
  ctrl$partition <- conversation_partition("chat", "test-user")

  user_turn <- list(
    class = "ellmer::UserTurn",
    version = 1,
    props = list(
      contents = list(
        list(
          class = "ellmer::ContentText",
          version = 1,
          props = list(text = "hi")
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
          props = list(text = "hello")
        )
      )
    )
  )
  ctrl$on_response(list(user_turn, asst_turn))

  # The out-of-band note has no matching turn group; it must land on the
  # fallback (current leaf) node, not get dropped.
  expect_equal(length(ctrl$record$nodes$n_0002$ui), 2)
  expect_equal(
    ctrl$record$nodes$n_0002$ui[[2]]$segments[[1]]$content,
    "Note: rate limit reset."
  )

  spy <- history_mock_session_with_spy()
  ctrl2 <- HistoryController$new(
    chat_id = "chat",
    client = mock_chat_client(),
    options = history_options(store = store, title = NULL),
    session = spy$session
  )
  ctrl2$partition <- conversation_partition("chat", "test-user")
  ctrl2$replay_ui(ctrl$record)

  sent <- history_spy_messages(spy)
  message_actions <- Filter(
    function(m) identical(m$message$action$type, "message"),
    sent
  )
  expect_length(message_actions, 3)
  expect_equal(
    message_actions[[3]]$message$action$message$segments[[1]]$content,
    "Note: rate limit reset."
  )
})

test_that("html_deps travel with a stored message and are resent on replay in a fresh session", {
  store <- InMemoryConversationStore$new()
  client <- mock_chat_client()
  session <- shiny::MockShinySession$new()
  dep <- list(
    name = "widgetdep",
    version = "1.0.0",
    src = list(href = "widgetdep"),
    stylesheet = "widget.css"
  )
  attachment <- list(
    mime = "text/plain",
    data_url = "data:text/plain;base64,aGk=",
    name = "note.txt",
    size = 2
  )
  get_chat_transcript(session, "chat")$replace(
    list(
      list(
        role = "assistant",
        segments = list(
          list(content = "<div>widget</div>", content_type = "html")
        ),
        htmlDeps = list(dep),
        attachments = list(attachment)
      )
    )
  )

  ctrl <- HistoryController$new(
    chat_id = "chat",
    client = client,
    options = history_options(store = store, title = NULL),
    session = session
  )
  ctrl$partition <- conversation_partition("chat", "test-user")
  asst_turn <- list(
    class = "ellmer::AssistantTurn",
    version = 1,
    props = list(
      contents = list(
        list(
          class = "ellmer::ContentText",
          version = 1,
          props = list(text = "widget")
        )
      )
    )
  )
  ctrl$on_response(list(asst_turn))
  expect_equal(ctrl$record$nodes$n_0001$ui[[1]]$htmlDeps, list(dep))

  # A brand-new session (e.g. a fresh browser tab) has no prior Shiny binding
  # state for this dependency -- replay must still re-send it.
  spy <- history_mock_session_with_spy()
  ctrl2 <- HistoryController$new(
    chat_id = "chat",
    client = mock_chat_client(),
    options = history_options(store = store, title = NULL),
    session = spy$session
  )
  ctrl2$partition <- conversation_partition("chat", "test-user")
  ctrl2$replay_ui(ctrl$record)

  sent <- history_spy_messages(spy)
  message_actions <- Filter(
    function(m) identical(m$message$action$type, "message"),
    sent
  )
  expect_length(message_actions, 1)
  expect_equal(message_actions[[1]]$message$html_deps, list(dep))
  expect_identical(
    get_chat_transcript(spy$session, "chat")$read(),
    list(
      list(
        role = "assistant",
        segments = list(
          list(content = "<div>widget</div>", content_type = "html")
        ),
        attachments = list(attachment),
        htmlDeps = list(dep)
      )
    )
  )
})

test_that("switching between two conversations repeatedly never duplicates or misattributes messages", {
  store <- InMemoryConversationStore$new()
  client <- mock_chat_client()
  session <- shiny::MockShinySession$new()

  ctrl <- HistoryController$new(
    chat_id = "chat",
    client = client,
    options = history_options(store = store, title = NULL),
    session = session
  )
  ctrl$partition <- conversation_partition("chat", "test-user")

  make_turn <- function(role, text) {
    class_name <- if (role == "user") {
      "ellmer::UserTurn"
    } else {
      "ellmer::AssistantTurn"
    }
    list(
      class = class_name,
      version = 1,
      props = list(
        contents = list(
          list(
            class = "ellmer::ContentText",
            version = 1,
            props = list(text = text)
          )
        )
      )
    )
  }

  make_ui_message <- function(role, text) {
    list(
      role = role,
      segments = list(list(content = text, content_type = "markdown"))
    )
  }

  set_transcript <- function(texts) {
    roles <- rep(c("user", "assistant"), length.out = length(texts))
    get_chat_transcript(session, "chat")$replace(
      Map(make_ui_message, roles, texts)
    )
  }

  # Collect the ui segment content for every node on a record's current path,
  # in order, so we can assert exact per-node content rather than a total.
  record_ui_texts <- function(record) {
    unlist(
      lapply(record_path_node_ids(record), function(node_id) {
        vapply(
          record$nodes[[node_id]]$ui,
          function(m) m$segments[[1]]$content,
          character(1)
        )
      })
    )
  }

  set_transcript(c("A", "B"))
  ctrl$on_response(list(make_turn("user", "A"), make_turn("assistant", "B")))
  conv1 <- ctrl$record

  ctrl$new_chat()
  set_transcript(c("C", "D"))
  ctrl$on_response(list(make_turn("user", "C"), make_turn("assistant", "D")))
  conv2 <- ctrl$record

  for (i in 1:3) {
    ctrl$switch_to(conv1$id)
    reloaded1 <- store$get(
      conversation_partition("chat", "test-user"),
      conv1$id
    )
    expect_equal(record_ui_count(reloaded1), 2)
    expect_equal(record_ui_texts(reloaded1), c("A", "B"))

    ctrl$switch_to(conv2$id)
    reloaded2 <- store$get(
      conversation_partition("chat", "test-user"),
      conv2$id
    )
    expect_equal(record_ui_count(reloaded2), 2)
    expect_equal(record_ui_texts(reloaded2), c("C", "D"))
  }

  # Prove growth after a switch is attached exactly once, not duplicated: go
  # back to conv1 and add one genuinely new turn/message pair.
  ctrl$switch_to(conv1$id)
  expect_equal(record_ui_count(ctrl$record), 2)

  new_turns <- c(
    record_path_turns(ctrl$record),
    list(make_turn("user", "E"))
  )
  client$set_turns(
    lapply(
      new_turns,
      ellmer::contents_replay,
      tools = client$get_tools()
    )
  )
  get_chat_transcript(session, "chat")$append(make_ui_message("user", "E"))
  ctrl$on_response(get_turns_recorded(client))

  reloaded1_grown <- store$get(
    conversation_partition("chat", "test-user"),
    conv1$id
  )
  expect_equal(record_ui_count(reloaded1_grown), 3)
  expect_equal(record_ui_texts(reloaded1_grown), c("A", "B", "E"))

  # conv2 must remain untouched by conv1's growth.
  reloaded2_final <- store$get(
    conversation_partition("chat", "test-user"),
    conv2$id
  )
  expect_equal(record_ui_count(reloaded2_final), 2)
  expect_equal(record_ui_texts(reloaded2_final), c("C", "D"))
})

test_that("on_evict fires before store$delete in evict_one and delete", {
  store <- InMemoryConversationStore$new()
  client <- mock_chat_client()
  session <- shiny::MockShinySession$new()

  ctrl <- HistoryController$new(
    chat_id = "chat",
    client = client,
    options = history_options(store = store, title = NULL),
    session = session
  )
  ctrl$partition <- conversation_partition("chat", "test-user")

  ctrl$on_response(make_turns("A", "B"))
  conv_id <- ctrl$record$id

  evict_saw_record_in_store <- NULL
  ctrl$on_evict <- function(id) {
    evict_saw_record_in_store <<- !is.null(
      store$get(conversation_partition("chat", "test-user"), id)
    )
  }

  ctrl$delete(conv_id)

  expect_true(evict_saw_record_in_store)
  expect_null(store$get(conversation_partition("chat", "test-user"), conv_id))
})

test_that("send_sibling_metadata() sends update_siblings with 0-based index/total for a branched path", {
  spy <- history_mock_session_with_spy()
  client <- mock_chat_client()
  store <- InMemoryConversationStore$new()

  ctrl <- HistoryController$new(
    chat_id = "chat",
    client = client,
    options = history_options(store = store, title = NULL),
    session = spy$session
  )
  ctrl$partition <- conversation_partition("chat", "test-user")

  rec <- new_conversation_record("test")
  rec$nodes <- list(
    n_0001 = list(
      parent = NULL,
      children = list("n_0002"),
      ui = list(list(role = "user"))
    ),
    n_0002 = list(
      parent = "n_0001",
      children = list(),
      ui = list(list(role = "assistant"))
    ),
    n_0003 = list(
      parent = NULL,
      children = list("n_0004"),
      ui = list(list(role = "user"))
    ),
    n_0004 = list(
      parent = "n_0003",
      children = list(),
      ui = list(list(role = "assistant"))
    )
  )
  rec$current_leaf <- "n_0004"
  ctrl$record <- rec

  ctrl$send_sibling_metadata()

  sent <- history_spy_messages(spy)
  update_siblings_msgs <- Filter(
    function(m) identical(m$message$action$type, "update_siblings"),
    sent
  )
  expect_length(update_siblings_msgs, 1)
  data <- update_siblings_msgs[[1]]$message$action$data
  expect_equal(data[["0"]]$index, 1L)
  expect_equal(data[["0"]]$total, 2L)
})

test_that("send_sibling_metadata() sends nothing when no path node has siblings", {
  spy <- history_mock_session_with_spy()
  client <- mock_chat_client()
  store <- InMemoryConversationStore$new()

  ctrl <- HistoryController$new(
    chat_id = "chat",
    client = client,
    options = history_options(store = store, title = NULL),
    session = spy$session
  )
  ctrl$partition <- conversation_partition("chat", "test-user")

  rec <- new_conversation_record("test")
  rec$nodes <- list(
    n_0001 = list(
      parent = NULL,
      children = list(),
      ui = list(list(role = "user"))
    )
  )
  rec$current_leaf <- "n_0001"
  ctrl$record <- rec

  ctrl$send_sibling_metadata()

  sent <- history_spy_messages(spy)
  update_siblings_msgs <- Filter(
    function(m) identical(m$message$action$type, "update_siblings"),
    sent
  )
  expect_length(update_siblings_msgs, 0)
})

test_that("handle_navigate() steps to the previous sibling branch and replays it", {
  spy <- history_mock_session_with_spy()
  client <- mock_chat_client()
  store <- InMemoryConversationStore$new()

  ctrl <- HistoryController$new(
    chat_id = "chat",
    client = client,
    options = history_options(store = store, title = NULL),
    session = spy$session
  )
  ctrl$partition <- conversation_partition("chat", "test-user")

  make_turn <- function(role, text) {
    class_name <- if (role == "user") {
      "ellmer::UserTurn"
    } else {
      "ellmer::AssistantTurn"
    }
    list(
      class = class_name,
      version = 1,
      props = list(
        contents = list(
          list(
            class = "ellmer::ContentText",
            version = 1,
            props = list(text = text)
          )
        )
      )
    )
  }
  make_ui_message <- function(role, text) {
    list(
      role = role,
      segments = list(list(content = text, content_type = "markdown"))
    )
  }
  set_transcript <- function(texts) {
    roles <- rep(c("user", "assistant"), length.out = length(texts))
    get_chat_transcript(spy$session, "chat")$replace(
      Map(make_ui_message, roles, texts)
    )
  }

  # First branch: "Hi" / "Hello"
  set_transcript(c("Hi", "Hello"))
  ctrl$on_response(
    list(
      make_turn("user", "Hi"),
      make_turn("assistant", "Hello")
    )
  )
  first_leaf <- ctrl$record$current_leaf
  first_root <- ctrl$record$nodes[[first_leaf]]$parent

  # Fork at the root by editing message 0 ("Hi"), then simulate the resubmit's
  # on_response with new turns "Hi again" / "New reply" -- this creates a
  # second root-level sibling.
  ctrl$handle_edit(0, "Hi again", NULL)
  set_transcript(c("Hi again", "New reply"))
  ctrl$on_response(
    list(
      make_turn("user", "Hi again"),
      make_turn("assistant", "New reply")
    )
  )
  second_leaf <- ctrl$record$current_leaf
  second_root <- ctrl$record$nodes[[second_leaf]]$parent

  expect_false(identical(first_root, second_root))
  expect_equal(ctrl$record$current_leaf, second_leaf)

  ctrl$handle_navigate(0, "prev")

  expect_equal(ctrl$record$current_leaf, first_leaf)
  expect_equal(
    record_path_turns(ctrl$record)[[1]]$props$contents[[1]]$props$text,
    "Hi"
  )
})

test_that("handle_navigate() is a no-op past the first/last sibling", {
  spy <- history_mock_session_with_spy()
  client <- mock_chat_client()
  store <- InMemoryConversationStore$new()

  ctrl <- HistoryController$new(
    chat_id = "chat",
    client = client,
    options = history_options(store = store, title = NULL),
    session = spy$session
  )
  ctrl$partition <- conversation_partition("chat", "test-user")

  rec <- new_conversation_record("test")
  rec$nodes <- list(
    n_0001 = list(
      parent = NULL,
      children = list(),
      turns = list(
        list(
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
      ),
      ui = list(
        list(
          role = "user",
          segments = list(list(content = "Hi", content_type = "markdown"))
        )
      )
    )
  )
  rec$current_leaf <- "n_0001"
  ctrl$record <- rec

  ctrl$handle_navigate(0, "prev")
  expect_equal(ctrl$record$current_leaf, "n_0001")

  ctrl$handle_navigate(0, "next")
  expect_equal(ctrl$record$current_leaf, "n_0001")
})

test_that("handle_edit() truncates current_leaf to the fork parent and resubmits via update_chat_user_input", {
  spy <- history_mock_session_with_spy()
  client <- mock_chat_client()
  store <- InMemoryConversationStore$new()

  ctrl <- HistoryController$new(
    chat_id = "chat",
    client = client,
    options = history_options(store = store, title = NULL),
    session = spy$session
  )
  ctrl$partition <- conversation_partition("chat", "test-user")

  make_turn <- function(role, text) {
    class_name <- if (role == "user") {
      "ellmer::UserTurn"
    } else {
      "ellmer::AssistantTurn"
    }
    list(
      class = class_name,
      version = 1,
      props = list(
        contents = list(
          list(
            class = "ellmer::ContentText",
            version = 1,
            props = list(text = text)
          )
        )
      )
    )
  }
  make_ui_message <- function(role, text) {
    list(
      role = role,
      segments = list(list(content = text, content_type = "markdown"))
    )
  }
  get_chat_transcript(spy$session, "chat")$replace(
    list(
      make_ui_message("user", "Hi"),
      make_ui_message("assistant", "Hello")
    )
  )
  ctrl$on_response(
    list(
      make_turn("user", "Hi"),
      make_turn("assistant", "Hello")
    )
  )

  user_node_id <- record_node_id_for_message_index(ctrl$record, 0)
  expect_null(ctrl$record$nodes[[user_node_id]]$parent)

  ctrl$handle_edit(0, "Hi again", NULL)

  # Truncated to the fork parent (root's parent is NULL here).
  expect_null(ctrl$record$current_leaf)

  sent <- history_spy_messages(spy)
  update_input_msgs <- Filter(
    function(m) identical(m$message$action$type, "update_input"),
    sent
  )
  expect_length(update_input_msgs, 1)
  expect_equal(update_input_msgs[[1]]$message$action$value, "Hi again")
  expect_true(isTRUE(update_input_msgs[[1]]$message$action$submit))
})

test_that("handle_edit() revalidates and forwards attachments with attachment_mode = set", {
  spy <- history_mock_session_with_spy()
  client <- mock_chat_client()
  store <- InMemoryConversationStore$new()

  ctrl <- HistoryController$new(
    chat_id = "chat",
    client = client,
    options = history_options(store = store, title = NULL),
    session = spy$session
  )
  ctrl$partition <- conversation_partition("chat", "test-user")

  make_turn <- function(role, text) {
    class_name <- if (role == "user") {
      "ellmer::UserTurn"
    } else {
      "ellmer::AssistantTurn"
    }
    list(
      class = class_name,
      version = 1,
      props = list(
        contents = list(
          list(
            class = "ellmer::ContentText",
            version = 1,
            props = list(text = text)
          )
        )
      )
    )
  }
  make_ui_message <- function(role, text) {
    list(
      role = role,
      segments = list(list(content = text, content_type = "markdown"))
    )
  }
  get_chat_transcript(spy$session, "chat")$replace(
    list(
      make_ui_message("user", "Hi"),
      make_ui_message("assistant", "Hello")
    )
  )
  ctrl$on_response(
    list(
      make_turn("user", "Hi"),
      make_turn("assistant", "Hello")
    )
  )

  attachments <- list(
    list(
      mime = "image/png",
      name = "a.png",
      size = 1L,
      data_url = "data:image/png;base64,AA=="
    )
  )

  ctrl$handle_edit(0, "see attached", attachments)

  sent <- history_spy_messages(spy)
  update_input_msgs <- Filter(
    function(m) identical(m$message$action$type, "update_input"),
    sent
  )
  expect_length(update_input_msgs, 1)
  expect_equal(
    update_input_msgs[[1]]$message$action$attachments[[1]]$name,
    "a.png"
  )
  expect_equal(update_input_msgs[[1]]$message$action$attachment_mode, "set")
})

test_that("handle_edit() forces attachment_mode = set for an empty-but-present attachments list", {
  spy <- history_mock_session_with_spy()
  client <- mock_chat_client()
  store <- InMemoryConversationStore$new()

  ctrl <- HistoryController$new(
    chat_id = "chat",
    client = client,
    options = history_options(store = store, title = NULL),
    session = spy$session
  )
  ctrl$partition <- conversation_partition("chat", "test-user")

  make_turn <- function(role, text) {
    class_name <- if (role == "user") {
      "ellmer::UserTurn"
    } else {
      "ellmer::AssistantTurn"
    }
    list(
      class = class_name,
      version = 1,
      props = list(
        contents = list(
          list(
            class = "ellmer::ContentText",
            version = 1,
            props = list(text = text)
          )
        )
      )
    )
  }
  make_ui_message <- function(role, text) {
    list(
      role = role,
      segments = list(list(content = text, content_type = "markdown"))
    )
  }
  get_chat_transcript(spy$session, "chat")$replace(
    list(
      make_ui_message("user", "Hi"),
      make_ui_message("assistant", "Hello")
    )
  )
  ctrl$on_response(
    list(
      make_turn("user", "Hi"),
      make_turn("assistant", "Hello")
    )
  )

  # Wire-realistic case: sendMessageEdit() always sends `attachments`,
  # defaulting to `[]`, which jsonlite deserializes to a non-NULL, length-0
  # list() -- not NULL.
  ctrl$handle_edit(0, "some content", list())

  sent <- history_spy_messages(spy)
  update_input_msgs <- Filter(
    function(m) identical(m$message$action$type, "update_input"),
    sent
  )
  expect_length(update_input_msgs, 1)
  expect_equal(update_input_msgs[[1]]$message$action$attachment_mode, "set")
  expect_equal(update_input_msgs[[1]]$message$action$attachments, list())
})

test_that("handle_edit() rejects unsupported attachment MIME types before resubmitting", {
  spy <- history_mock_session_with_spy()
  client <- mock_chat_client()
  store <- InMemoryConversationStore$new()

  ctrl <- HistoryController$new(
    chat_id = "chat",
    client = client,
    options = history_options(store = store, title = NULL),
    session = spy$session
  )
  ctrl$partition <- conversation_partition("chat", "test-user")

  make_turn <- function(role, text) {
    class_name <- if (role == "user") {
      "ellmer::UserTurn"
    } else {
      "ellmer::AssistantTurn"
    }
    list(
      class = class_name,
      version = 1,
      props = list(
        contents = list(
          list(
            class = "ellmer::ContentText",
            version = 1,
            props = list(text = text)
          )
        )
      )
    )
  }
  make_ui_message <- function(role, text) {
    list(
      role = role,
      segments = list(list(content = text, content_type = "markdown"))
    )
  }
  get_chat_transcript(spy$session, "chat")$replace(
    list(
      make_ui_message("user", "Hi"),
      make_ui_message("assistant", "Hello")
    )
  )
  ctrl$on_response(
    list(
      make_turn("user", "Hi"),
      make_turn("assistant", "Hello")
    )
  )

  bad_attachments <- list(
    list(
      mime = "application/octet-stream",
      name = "x.bin",
      size = 1L,
      data_url = "data:application/octet-stream;base64,AA=="
    )
  )

  expect_error(
    ctrl$handle_edit(0, "see attached", bad_attachments),
    "unsupported MIME type"
  )
})
