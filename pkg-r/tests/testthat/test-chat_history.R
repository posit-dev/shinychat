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

test_that("notify_settled() calls on_settled hook", {
  store <- InMemoryConversationStore$new()
  client <- mock_chat_client()
  session <- shiny::MockShinySession$new()

  ctrl <- HistoryController$new(
    chat_id = "chat",
    client = client,
    options = history_options(store = store, title = NULL),
    session = session
  )

  calls <- list()
  ctrl$on_settled <- function(restored) {
    calls[[length(calls) + 1]] <<- restored
  }

  ctrl$notify_settled(TRUE)
  ctrl$notify_settled(FALSE)

  expect_equal(calls, list(TRUE, FALSE))
})

test_that("notify_settled() is a no-op when on_settled is unset", {
  store <- InMemoryConversationStore$new()
  client <- mock_chat_client()
  session <- shiny::MockShinySession$new()

  ctrl <- HistoryController$new(
    chat_id = "chat",
    client = client,
    options = history_options(store = store, title = NULL),
    session = session
  )

  expect_no_error(ctrl$notify_settled(TRUE))
})

test_that("new_chat() notifies on_settled with FALSE", {
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

  calls <- list()
  ctrl$on_settled <- function(restored) {
    calls[[length(calls) + 1]] <<- restored
  }

  ctrl$new_chat()

  expect_equal(calls, list(FALSE))
})

test_that("replay_ui() clears the greeting", {
  spy <- history_mock_session_with_spy()
  store <- InMemoryConversationStore$new()
  client <- mock_chat_client()

  ctrl <- HistoryController$new(
    chat_id = "chat",
    client = client,
    options = history_options(store = store, title = NULL),
    session = spy$session
  )
  ctrl$partition <- conversation_partition("chat", "test-user")

  record <- new_conversation_record(title = "t")
  ctrl$replay_ui(record)

  messages <- history_spy_messages(spy)
  types <- vapply(
    messages,
    function(m) m$message$action$type,
    character(1)
  )
  expect_true("greeting_clear" %in% types)
})

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

  expect_false(is.null(ctrl$record))
  expect_equal(ctrl$record$title, "Hello")
  expect_equal(length(ctrl$record$nodes), 2)
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
  ctrl$partition <- conversation_partition("chat", "test-user")
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
  expect_length(store$list(conversation_partition("chat", "test-user")), 0)
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

test_that("HistoryController$switch_to() rejects an unsupported schema_version from a custom store", {
  BadSchemaStore <- R6::R6Class(
    "BadSchemaStore",
    inherit = ConversationStore,
    public = list(
      list = function(partition) {
        list(new_conversation_meta(
          id = "bad-id",
          title = "bad",
          created_at = "2026-01-01T00:00:00Z",
          updated_at = "2026-01-01T00:00:00Z",
          size_bytes = 0
        ))
      },
      get = function(partition, id) {
        rec <- new_conversation_record("bad")
        rec$id <- id
        rec$schema_version <- 99L
        rec
      },
      put = function(partition, record) invisible(NULL),
      delete = function(partition, id) invisible(NULL)
    )
  )

  store <- BadSchemaStore$new()
  client <- mock_chat_client()
  session <- shiny::MockShinySession$new()

  ctrl <- HistoryController$new(
    chat_id = "chat",
    client = client,
    options = history_options(store = store, title = NULL),
    session = session
  )
  ctrl$partition <- conversation_partition("chat", "test-user")

  expect_error(
    ctrl$switch_to("bad-id"),
    class = "shinychat_error_unsupported_schema_version"
  )
})

test_that("HistoryController$rename() rejects an unsupported schema_version before writing", {
  # The controller must check schema_version on every write, not just every
  # read -- a custom store's put() should never see an incompatible record
  # (issue #322).
  RecordingStore <- R6::R6Class(
    "RecordingStore",
    inherit = ConversationStore,
    public = list(
      put_calls = list(),
      list = function(partition) list(),
      get = function(partition, id) NULL,
      put = function(partition, record) {
        self$put_calls[[length(self$put_calls) + 1L]] <- record
        invisible(NULL)
      },
      delete = function(partition, id) invisible(NULL)
    )
  )

  store <- RecordingStore$new()
  client <- mock_chat_client()
  session <- shiny::MockShinySession$new()

  ctrl <- HistoryController$new(
    chat_id = "chat",
    client = client,
    options = history_options(store = store, title = NULL),
    session = session
  )
  ctrl$partition <- conversation_partition("chat", "test-user")
  ctrl$record <- new_conversation_record("bad")
  ctrl$record$schema_version <- 99L

  expect_error(
    ctrl$rename(ctrl$record$id, "new title"),
    class = "shinychat_error_unsupported_schema_version"
  )
  expect_length(store$put_calls, 0L)
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

test_that("bookmark mode on_response_saved works from a module session", {
  # Shiny's module session proxy forbids onBookmarked():
  #   stop("onBookmarked() can't be used in a module.")
  # (shiny/R/shiny.R, in makeScope()). MockShinySession$makeScope() doesn't
  # emulate that restriction, so build a faithful proxy by hand.
  root <- shiny::MockShinySession$new()

  registered_on <- NULL
  # MockShinySession$onBookmarked() is a noop returning NULL; give it a
  # realistic cancel-function return value and record which session the
  # callback was registered on.
  root$onBookmarked <- function(fun) {
    registered_on <<- "root"
    function() invisible(NULL)
  }

  mod_session <- shiny:::createSessionProxy(
    root,
    ns = shiny::NS("mod"),
    onBookmarked = function(fun) {
      stop("onBookmarked() can't be used in a module.")
    }
  )

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
    session = mod_session
  )

  ctrl <- get_session_chat_bookmark_info(mod_session, "chat.history-controller")
  record <- new_conversation_record("conv1")

  expect_no_error(ctrl$on_response_saved(record))
  expect_identical(registered_on, "root")
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

test_that("HistoryController$on_response() attaches client-reported messages to nodes", {
  store <- InMemoryConversationStore$new()
  client <- mock_chat_client()
  session <- shiny::MockShinySession$new()
  session$setInputs(
    chat_messages = list(
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
  expect_equal(ctrl$ui_offset, 2)
})

test_that("HistoryController$on_response() is idempotent when neither turns nor messages grew", {
  store <- InMemoryConversationStore$new()
  client <- mock_chat_client()
  session <- shiny::MockShinySession$new()
  session$setInputs(
    chat_messages = list(
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

test_that("on_response() idempotent guard advances ui_offset so a later genuine save does not duplicate stored UI", {
  # Regression test: the idempotency guard in on_response() must advance
  # self$ui_offset to length(messages) before its early return. Without
  # that, a restore-triggered client re-report (same turns/messages) leaves
  # a stale ui_offset (0), and the next genuine save reprocesses the
  # already-saved client-snapshot messages as out-of-band extras in
  # extend_record_linear(), duplicating them in the stored UI (6 instead
  # of 4).
  store <- InMemoryConversationStore$new()
  client <- mock_chat_client()
  session <- shiny::MockShinySession$new()

  make_ui_message <- function(role, text) {
    list(
      role = role,
      segments = list(list(content = text, content_type = "markdown"))
    )
  }

  # Helper: set the mock session's reported chat_messages for a given set
  # of (role, text) pairs.
  report_client_messages <- function(texts) {
    roles <- rep(c("user", "assistant"), length.out = length(texts))
    session$setInputs(
      chat_messages = Map(make_ui_message, roles, texts)
    )
  }

  ctrl <- HistoryController$new(
    chat_id = "chat",
    client = client,
    options = history_options(store = store, title = NULL),
    session = session
  )
  ctrl$partition <- conversation_partition("chat", "test-user")

  # --- Step 1: Save one user/assistant exchange (2 messages) ---
  report_client_messages(c("Hello", "Hi there"))
  ctrl$on_response(make_turns("Hello", "Hi there"))

  expect_equal(length(ctrl$record$nodes), 2)
  expect_equal(ctrl$ui_offset, 2)
  expect_equal(record_ui_count(ctrl$record), 2)

  # --- Step 2: Simulate a restore-triggered re-report of the same turns ---
  # The idempotent guard fires (turns and messages did not grow). Without
  # the fix, ui_offset would stay stale at 0 (or whatever it was before).
  updated_at_before <- ctrl$record$updated_at
  ctrl$on_response(make_turns("Hello", "Hi there"))

  # No new save happened: the record is untouched.
  expect_identical(ctrl$record$updated_at, updated_at_before)
  expect_equal(length(ctrl$record$nodes), 2)
  # The guard must have advanced ui_offset to match the reported messages.
  expect_equal(ctrl$ui_offset, 2)

  # --- Step 3: Genuine new save with a second exchange (4 messages) ---
  report_client_messages(c("Hello", "Hi there", "How are you?", "I'm good"))
  all_turns <- c(
    make_turns("Hello", "Hi there"),
    make_turns("How are you?", "I'm good")
  )
  ctrl$on_response(all_turns)

  # The record should have exactly 4 UI messages — 2 per exchange, no
  # duplicates. The bug (stale ui_offset == 0) would reprocess the first
  # 2 already-saved messages as out-of-band extras, producing 6.
  expect_equal(length(ctrl$record$nodes), 4)
  expect_equal(record_ui_count(ctrl$record), 4)
  expect_equal(ctrl$ui_offset, 4)

  # Assert the exact per-node UI content to prove no duplication: each
  # node carries exactly one message with the expected text.
  path_ids <- record_path_node_ids(ctrl$record)
  ui_texts <- unlist(lapply(path_ids, function(node_id) {
    vapply(
      ctrl$record$nodes[[node_id]]$ui,
      function(m) m$segments[[1]]$content,
      character(1)
    )
  }))
  expect_equal(ui_texts, c("Hello", "Hi there", "How are you?", "I'm good"))
})

test_that("HistoryController$replay_ui() replays stored ui verbatim and seeds ui_offset from the restore count", {
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

  expect_equal(ctrl$ui_offset, 1)
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
  expect_equal(ctrl$ui_offset, 1)
})

test_that("an out-of-band message survives a conversation switch and restore", {
  store <- InMemoryConversationStore$new()
  client <- mock_chat_client()
  session <- shiny::MockShinySession$new()
  session$setInputs(
    chat_messages = list(
      list(
        role = "user",
        segments = list(list(content = "hi", content_type = "markdown"))
      ),
      list(
        role = "assistant",
        segments = list(list(content = "hello", content_type = "markdown"))
      ),
      # Reported by the client even though it isn't part of an LLM turn --
      # e.g. injected via chat_append_message() outside the on_user_submit flow.
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

test_that("html_deps from server-derived content travel with a stored message and are resent on replay", {
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

  # With P4, UI is server-derived from turns. A plain ContentText turn
  # produces a markdown string segment with no html deps. The stored message
  # carries the version marker and the turn's text.
  stored <- ctrl$record$nodes$n_0001$ui[[1]]
  expect_equal(stored$version, STORED_UI_VERSION)
  expect_equal(stored$role, "assistant")
  expect_equal(stored$segments[[1]]$content, "widget")
  expect_equal(stored$segments[[1]]$content_type, "markdown")

  # Replay in a fresh session re-sends the stored message
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
  expect_equal(
    message_actions[[1]]$message$action$message$segments[[1]]$content,
    "widget"
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

  # What a real client would report for `texts`: one ui message per text,
  # alternating user/assistant starting with "user" -- i.e. exactly what
  # replay_ui() would have just re-sent to the browser for this conversation.
  report_client_messages <- function(texts) {
    roles <- rep(c("user", "assistant"), length.out = length(texts))
    session$setInputs(
      chat_messages = Map(make_ui_message, roles, texts)
    )
  }

  # Collect the ui segment content for every node on a record's current path,
  # in order, so we can assert exact per-node content rather than a total.
  record_ui_texts <- function(record) {
    unlist(lapply(record_path_node_ids(record), function(node_id) {
      vapply(
        record$nodes[[node_id]]$ui,
        function(m) m$segments[[1]]$content,
        character(1)
      )
    }))
  }

  report_client_messages(c("A", "B"))
  ctrl$on_response(list(make_turn("user", "A"), make_turn("assistant", "B")))
  conv1 <- ctrl$record

  ctrl$new_chat()
  report_client_messages(c("C", "D"))
  ctrl$on_response(list(make_turn("user", "C"), make_turn("assistant", "D")))
  conv2 <- ctrl$record

  # Switch back and forth several times. Each switch_to() first calls
  # save_current() against whatever the mock session currently reports for
  # `chat_messages` -- so it must be refreshed to what *that* conversation's
  # client would actually echo back after being restored, not left stale from
  # the other conversation. This exercises the idempotency path in
  # save_current()/extend_record_linear() for real (non-empty-diff) inputs.
  for (i in 1:3) {
    report_client_messages(c("A", "B"))
    ctrl$switch_to(conv1$id)
    reloaded1 <- store$get(
      conversation_partition("chat", "test-user"),
      conv1$id
    )
    expect_equal(record_ui_count(reloaded1), 2)
    expect_equal(record_ui_texts(reloaded1), c("A", "B"))

    report_client_messages(c("C", "D"))
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
  report_client_messages(c("A", "B"))
  ctrl$switch_to(conv1$id)

  # switch_to()'s replay marks the *next* on_response() call as a suppressed
  # echo of the replay itself (see suppress_next_save in chat_history.R), and
  # only clears is_replaying once the mock session flushes. A real client's
  # async echo of the replay -- and the flush it rides in on -- arrive before
  # any genuinely new turn can, so simulate that here (as a no-op) before
  # exercising real growth below.
  report_client_messages(c("A", "B"))
  ctrl$on_response(get_turns_recorded(client))
  expect_equal(record_ui_count(ctrl$record), 2)

  new_turns <- c(
    record_path_turns(ctrl$record),
    list(make_turn("user", "E"))
  )
  client$set_turns(lapply(
    new_turns,
    ellmer::contents_replay,
    tools = client$get_tools()
  ))
  report_client_messages(c("A", "B", "E"))
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
  report_client_messages <- function(texts) {
    roles <- rep(c("user", "assistant"), length.out = length(texts))
    spy$session$setInputs(chat_messages = Map(make_ui_message, roles, texts))
  }

  # First branch: "Hi" / "Hello"
  report_client_messages(c("Hi", "Hello"))
  ctrl$on_response(list(
    make_turn("user", "Hi"),
    make_turn("assistant", "Hello")
  ))
  first_leaf <- ctrl$record$current_leaf
  first_root <- ctrl$record$nodes[[first_leaf]]$parent

  # Fork at the root by editing message 0 ("Hi"), then simulate the resubmit's
  # on_response with new turns "Hi again" / "New reply" -- this creates a
  # second root-level sibling.
  ctrl$handle_edit(0, "Hi again", NULL)
  report_client_messages(c("Hi again", "New reply"))
  ctrl$on_response(list(
    make_turn("user", "Hi again"),
    make_turn("assistant", "New reply")
  ))
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
      turns = list(list(
        class = "ellmer::UserTurn",
        version = 1,
        props = list(
          contents = list(list(
            class = "ellmer::ContentText",
            version = 1,
            props = list(text = "Hi")
          ))
        )
      )),
      ui = list(list(
        role = "user",
        segments = list(list(content = "Hi", content_type = "markdown"))
      ))
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
  spy$session$setInputs(
    chat_messages = list(
      make_ui_message("user", "Hi"),
      make_ui_message("assistant", "Hello")
    )
  )
  ctrl$on_response(list(
    make_turn("user", "Hi"),
    make_turn("assistant", "Hello")
  ))

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
        contents = list(list(
          class = "ellmer::ContentText",
          version = 1,
          props = list(text = text)
        ))
      )
    )
  }
  make_ui_message <- function(role, text) {
    list(
      role = role,
      segments = list(list(content = text, content_type = "markdown"))
    )
  }
  spy$session$setInputs(
    chat_messages = list(
      make_ui_message("user", "Hi"),
      make_ui_message("assistant", "Hello")
    )
  )
  ctrl$on_response(list(
    make_turn("user", "Hi"),
    make_turn("assistant", "Hello")
  ))

  attachments <- list(list(
    mime = "image/png",
    name = "a.png",
    size = 1L,
    data_url = "data:image/png;base64,AA=="
  ))

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
        contents = list(list(
          class = "ellmer::ContentText",
          version = 1,
          props = list(text = text)
        ))
      )
    )
  }
  make_ui_message <- function(role, text) {
    list(
      role = role,
      segments = list(list(content = text, content_type = "markdown"))
    )
  }
  spy$session$setInputs(
    chat_messages = list(
      make_ui_message("user", "Hi"),
      make_ui_message("assistant", "Hello")
    )
  )
  ctrl$on_response(list(
    make_turn("user", "Hi"),
    make_turn("assistant", "Hello")
  ))

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
        contents = list(list(
          class = "ellmer::ContentText",
          version = 1,
          props = list(text = text)
        ))
      )
    )
  }
  make_ui_message <- function(role, text) {
    list(
      role = role,
      segments = list(list(content = text, content_type = "markdown"))
    )
  }
  spy$session$setInputs(
    chat_messages = list(
      make_ui_message("user", "Hi"),
      make_ui_message("assistant", "Hello")
    )
  )
  ctrl$on_response(list(
    make_turn("user", "Hi"),
    make_turn("assistant", "Hello")
  ))

  bad_attachments <- list(list(
    mime = "application/octet-stream",
    name = "x.bin",
    size = 1L,
    data_url = "data:application/octet-stream;base64,AA=="
  ))

  expect_error(
    ctrl$handle_edit(0, "see attached", bad_attachments),
    "unsupported MIME type"
  )
})

# --- P4: turns-based restore tests ---

# Fixtures for tool-carrying turns, using recorded (serialized) turn
# representations that contents_replay() can reconstruct.
make_tool_turns <- function(
  user_text = "what's the weather?",
  asst_text = "Let me check.",
  result_value = "Sunny, 75F",
  final_text = "It's sunny and 75F!"
) {
  user_turn <- list(
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
  )
  tool_request_turn <- list(
    class = "ellmer::AssistantTurn",
    version = 1,
    props = list(
      contents = list(
        list(
          class = "ellmer::ContentText",
          version = 1,
          props = list(text = asst_text)
        ),
        list(
          class = "ellmer::ContentToolRequest",
          version = 1,
          props = list(
            id = "t1",
            name = "get_weather",
            arguments = list(),
            extra = list()
          )
        )
      )
    )
  )
  tool_result_turn <- list(
    class = "ellmer::UserTurn",
    version = 1,
    props = list(
      contents = list(
        list(
          class = "ellmer::ContentToolResult",
          version = 1,
          props = list(
            value = result_value,
            extra = list(),
            request = list(
              class = "ellmer::ContentToolRequest",
              version = 1,
              props = list(
                id = "t1",
                name = "get_weather",
                arguments = list(),
                extra = list()
              )
            )
          )
        )
      )
    )
  )
  final_turn <- list(
    class = "ellmer::AssistantTurn",
    version = 1,
    props = list(
      contents = list(
        list(
          class = "ellmer::ContentText",
          version = 1,
          props = list(text = final_text)
        )
      )
    )
  )
  list(user_turn, tool_request_turn, tool_result_turn, final_turn)
}

test_that("saving after a tool request+result stores UI with structured blocks and block_positions", {
  store <- InMemoryConversationStore$new()
  client <- mock_chat_client()
  session <- shiny::MockShinySession$new()
  session$setInputs(
    chat_messages = list(
      list(
        role = "user",
        segments = list(list(
          content = "what's the weather?",
          content_type = "markdown"
        ))
      ),
      list(
        role = "assistant",
        segments = list(list(
          content = "It's sunny and 75F!",
          content_type = "markdown"
        ))
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

  turns <- make_tool_turns()
  ctrl$on_response(turns)

  # n_0001 is the user turn group: one derived message
  expect_equal(ctrl$record$nodes$n_0001$ui[[1]]$version, STORED_UI_VERSION)
  expect_equal(ctrl$record$nodes$n_0001$ui[[1]]$role, "user")
  expect_equal(
    ctrl$record$nodes$n_0001$ui[[1]]$segments[[1]]$content,
    "what's the weather?"
  )

  # n_0002 is the assistant+tool group: one derived message with blocks
  derived <- ctrl$record$nodes$n_0002$ui[[1]]
  expect_equal(derived$version, STORED_UI_VERSION)
  expect_equal(derived$role, "assistant")
  expect_false(is.null(derived$blocks))
  expect_true(length(derived$blocks) >= 2)

  # The tool_request and tool_result blocks are present
  block_types <- vapply(derived$blocks, function(b) b$type, character(1))
  expect_true("tool_request" %in% block_types)
  expect_true("tool_result" %in% block_types)

  # block_positions records how many string segments precede each block
  expect_false(is.null(derived$block_positions))
  expect_length(derived$block_positions, length(derived$blocks))

  # The tool_request block has the correct request_id and tool_name
  req_block <- derived$blocks[[which(block_types == "tool_request")[1]]]
  expect_equal(req_block$request_id, "t1")
  expect_equal(req_block$tool_name, "get_weather")
  expect_equal(req_block$version, 1L)

  # The tool_result block has the correct request_id and status
  res_block <- derived$blocks[[which(block_types == "tool_result")[1]]]
  expect_equal(res_block$request_id, "t1")
  expect_equal(res_block$tool_name, "get_weather")
  expect_equal(res_block$status, "success")
  expect_equal(res_block$version, 1L)
})

test_that("replay emits message actions with structured blocks inline in segments", {
  store <- InMemoryConversationStore$new()
  client <- mock_chat_client()
  session <- shiny::MockShinySession$new()
  session$setInputs(
    chat_messages = list(
      list(
        role = "user",
        segments = list(list(
          content = "what's the weather?",
          content_type = "markdown"
        ))
      ),
      list(
        role = "assistant",
        segments = list(list(
          content = "It's sunny and 75F!",
          content_type = "markdown"
        ))
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

  turns <- make_tool_turns()
  ctrl$on_response(turns)

  # Replay in a fresh session
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
  # Two messages: user + assistant (with blocks)
  expect_length(message_actions, 2)

  # The assistant message's segments include structured blocks inline
  asst_segments <- message_actions[[2]]$message$action$message$segments
  # Find the blocks in the segments (they have a "type" field)
  block_segs <- Filter(function(s) "type" %in% names(s), asst_segments)
  expect_true(length(block_segs) >= 2)
  block_types <- vapply(block_segs, function(s) s$type, character(1))
  expect_true("tool_request" %in% block_types)
  expect_true("tool_result" %in% block_types)

  # The assistant text is also present as a string segment
  string_segs <- Filter(function(s) !"type" %in% names(s), asst_segments)
  seg_contents <- vapply(string_segs, function(s) s$content, character(1))
  expect_true("It's sunny and 75F!" %in% seg_contents)
})

test_that("old-format stored UI (no version marker) is discarded and re-derived from turns", {
  store <- InMemoryConversationStore$new()
  client <- mock_chat_client()
  spy <- history_mock_session_with_spy()

  ctrl <- HistoryController$new(
    chat_id = "chat",
    client = client,
    options = history_options(store = store, title = NULL),
    session = spy$session
  )
  ctrl$partition <- conversation_partition("chat", "test-user")

  # Build a record with old-format UI (string-only, no version marker)
  turns <- make_tool_turns()
  rec <- new_conversation_record("test")
  rec$nodes <- list(
    n_0001 = list(
      parent = NULL,
      children = list("n_0002"),
      turns = list(turns[[1]]),
      ui = list(list(
        role = "user",
        segments = list(list(
          content = "what's the weather?",
          content_type = "markdown"
        ))
      ))
    ),
    n_0002 = list(
      parent = "n_0001",
      children = list(),
      turns = turns[2:4],
      # Old-format UI: string-only, no version marker, no blocks
      ui = list(list(
        role = "assistant",
        segments = list(list(
          content = "Let me check. [tool card] It's sunny!",
          content_type = "markdown"
        ))
      ))
    )
  )
  rec$current_leaf <- "n_0002"

  ctrl$replay_ui(rec)

  sent <- history_spy_messages(spy)
  message_actions <- Filter(
    function(m) identical(m$message$action$type, "message"),
    sent
  )
  expect_length(message_actions, 2)

  # The assistant message (second) should have structured blocks, not
  # the old string-only markup
  asst_segments <- message_actions[[2]]$message$action$message$segments
  block_segs <- Filter(function(s) "type" %in% names(s), asst_segments)
  expect_true(length(block_segs) >= 2)
  block_types <- vapply(block_segs, function(s) s$type, character(1))
  expect_true("tool_request" %in% block_types)
  expect_true("tool_result" %in% block_types)
})

test_that("node with neither usable UI nor turns falls back to text-only", {
  store <- InMemoryConversationStore$new()
  client <- mock_chat_client()
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
      turns = list(),
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
  # Text-only fallback: empty content
  expect_equal(
    message_actions[[1]]$message$action$message$segments[[1]]$content,
    ""
  )
})

test_that("offset/bookkeeping stays correct across a save-replay-continue-save cycle", {
  store <- InMemoryConversationStore$new()
  client <- mock_chat_client()

  # --- First session: save a conversation with tool turns ---
  session1 <- shiny::MockShinySession$new()
  session1$setInputs(
    chat_messages = list(
      list(
        role = "user",
        segments = list(list(
          content = "what's the weather?",
          content_type = "markdown"
        ))
      ),
      list(
        role = "assistant",
        segments = list(list(
          content = "It's sunny and 75F!",
          content_type = "markdown"
        ))
      )
    )
  )

  ctrl1 <- HistoryController$new(
    chat_id = "chat",
    client = client,
    options = history_options(store = store, title = NULL),
    session = session1
  )
  ctrl1$partition <- conversation_partition("chat", "test-user")

  turns1 <- make_tool_turns()
  ctrl1$on_response(turns1)
  conv_id <- ctrl1$record$id
  expect_equal(ctrl1$ui_offset, 2)

  # --- Second session: restore and continue ---
  spy <- history_mock_session_with_spy()
  ctrl2 <- HistoryController$new(
    chat_id = "chat",
    client = mock_chat_client(),
    options = history_options(store = store, title = NULL),
    session = spy$session
  )
  ctrl2$partition <- conversation_partition("chat", "test-user")
  ctrl2$replay_ui(ctrl1$record)
  ctrl2$record <- ctrl1$record

  # ui_offset should reflect the 2 messages replayed
  expect_equal(ctrl2$ui_offset, 2)

  # Continue: add a new turn pair
  new_turns <- c(
    record_path_turns(ctrl1$record),
    list(
      list(
        class = "ellmer::UserTurn",
        version = 1,
        props = list(
          contents = list(list(
            class = "ellmer::ContentText",
            version = 1,
            props = list(text = "thanks!")
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
            props = list(text = "You're welcome!")
          ))
        )
      )
    )
  )

  # Set up the client with the restored turns + new turns
  ctrl2$get_client()$set_turns(lapply(
    new_turns,
    ellmer::contents_replay,
    tools = ctrl2$get_client()$get_tools()
  ))

  # Simulate the client reporting 4 messages (2 restored + 2 new)
  spy$session$setInputs(
    chat_messages = list(
      list(
        role = "user",
        segments = list(list(
          content = "what's the weather?",
          content_type = "markdown"
        ))
      ),
      list(
        role = "assistant",
        segments = list(list(
          content = "It's sunny and 75F!",
          content_type = "markdown"
        ))
      ),
      list(
        role = "user",
        segments = list(list(
          content = "thanks!",
          content_type = "markdown"
        ))
      ),
      list(
        role = "assistant",
        segments = list(list(
          content = "You're welcome!",
          content_type = "markdown"
        ))
      )
    )
  )

  # The first on_response after replay is the replay echo (suppressed).
  # This mirrors the real flow: replay_ui sets suppress_next_save = TRUE,
  # and the first post-replay on_response swallows the echo.
  ctrl2$on_response(get_turns_recorded(ctrl2$get_client()))
  expect_equal(length(ctrl2$record$nodes), 2) # unchanged

  # The second on_response is the real new response
  ctrl2$on_response(get_turns_recorded(ctrl2$get_client()))

  # The record should now have 4 nodes, 4 UI messages
  expect_equal(length(ctrl2$record$nodes), 4)
  expect_equal(record_ui_count(ctrl2$record), 4)
  expect_equal(ctrl2$ui_offset, 4)

  # The new nodes have derived UI with version markers
  expect_equal(
    ctrl2$record$nodes$n_0003$ui[[1]]$version,
    STORED_UI_VERSION
  )
  expect_equal(
    ctrl2$record$nodes$n_0003$ui[[1]]$segments[[1]]$content,
    "thanks!"
  )
  expect_equal(
    ctrl2$record$nodes$n_0004$ui[[1]]$segments[[1]]$content,
    "You're welcome!"
  )
})
