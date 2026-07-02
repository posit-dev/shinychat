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

test_that("chat_server() accepts history = TRUE", {
  skip_if_not_installed("ellmer")

  client <- mock_chat_client()

  shiny::testServer(
    function(input, output, session) {
      chat_server("chat", client, history = TRUE, session = session)
    },
    {
      expect_true(TRUE)
    }
  )
})

test_that("chat_server() accepts history = FALSE", {
  skip_if_not_installed("ellmer")

  client <- mock_chat_client()

  shiny::testServer(
    function(input, output, session) {
      chat_server("chat", client, history = FALSE, session = session)
    },
    {
      expect_true(TRUE)
    }
  )
})

test_that("chat_server() accepts history = history_options() config", {
  skip_if_not_installed("ellmer")

  client <- mock_chat_client()
  config <- history_options(store = "memory", max_store_mb = 10)

  shiny::testServer(
    function(input, output, session) {
      chat_server("chat", client, history = config, session = session)
    },
    {
      expect_true(TRUE)
    }
  )
})

test_that("chat_server() with a non-default module id wires on_save/on_restore to the live controller", {
  # Regression: chat_app.R used to look up the controller under the hardcoded
  # key "chat.history-controller" instead of paste0(id, ".history-controller"),
  # so on_save()/on_restore() silently no-oped for any id != "chat".
  skip_if_not_installed("ellmer")

  client <- mock_chat_client()

  shiny::testServer(
    function(input, output, session) {
      mod <- chat_server("mychat", client, history = TRUE, session = session)
      mod$history$on_save(function(values) values)
      mod$history$on_restore(function(values) values)
    },
    {
      ctrl <- get_session_chat_bookmark_info(
        session,
        "mychat.history-controller"
      )
      expect_false(is.null(ctrl))
      expect_false(is.null(ctrl$.__enclos_env__$private$on_save))
      expect_false(is.null(ctrl$.__enclos_env__$private$on_restore))
    }
  )
})

test_that("HistoryController stores responses in assigned partition", {
  store <- InMemoryConversationStore$new()
  ctrl <- HistoryController$new(
    chat_id = "ns-chat",
    client = mock_chat_client(),
    options = history_options(store = store, title = NULL),
    session = shiny::MockShinySession$new()
  )
  ctrl$partition <- conversation_partition("ns-chat", "browser-1")

  turns <- list(
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
    ),
    list(
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
  )
  ctrl$on_response(turns)

  expect_equal(
    store$list(conversation_partition("ns-chat", "browser-1"))[[1]]$id,
    ctrl$record$id
  )
  expect_length(
    store$list(conversation_partition("other-chat", "browser-1")),
    0
  )
})

test_that("same scope with different chat ids is isolated", {
  store <- InMemoryConversationStore$new()
  rec <- new_conversation_record("chat a")
  store$put(conversation_partition("chat-a", "browser-1"), rec)

  expect_equal(
    store$get(conversation_partition("chat-a", "browser-1"), rec$id)$id,
    rec$id
  )
  expect_null(store$get(conversation_partition("chat-b", "browser-1"), rec$id))
  expect_length(store$list(conversation_partition("chat-b", "browser-1")), 0)
})

test_that("namespaced chat ids are distinct partitions", {
  store <- InMemoryConversationStore$new()
  rec <- new_conversation_record("module one")
  ns1 <- conversation_partition("mod1-chat", "browser-1")
  ns2 <- conversation_partition("mod2-chat", "browser-1")

  store$put(ns1, rec)

  expect_equal(store$get(ns1, rec$id)$id, rec$id)
  expect_null(store$get(ns2, rec$id))
})

test_that("chat_enable_history uses resolved id for partition chat id", {
  skip_if_not_installed("ellmer")

  store <- InMemoryConversationStore$new()
  client <- mock_chat_client()

  shiny::testServer(
    function(input, output, session) {
      chat_enable_history(
        "mod-chat",
        client,
        options = history_options(
          store = store,
          scope = "browser-1",
          title = NULL
        ),
        session = session
      )
    },
    {
      ctrl <- get_session_chat_bookmark_info(
        session,
        "mod-chat.history-controller"
      )

      session$setInputs("mod-chat_history_browser_token" = "tok-abc")

      expect_equal(ctrl$partition$chat_id, session$ns("mod-chat"))
      expect_equal(ctrl$partition$scope, "browser-1")

      ctrl$on_response(list())

      expect_equal(
        store$list(
          conversation_partition(session$ns("mod-chat"), "browser-1")
        )[[1]]$id,
        ctrl$record$id
      )
      expect_length(
        store$list(conversation_partition("chat", "browser-1")),
        0
      )
    }
  )
})

test_that("chat_enable_history uses module namespace in partition chat id", {
  skip_if_not_installed("ellmer")

  store <- InMemoryConversationStore$new()
  client <- mock_chat_client()

  chat_mod <- function(id) {
    shiny::moduleServer(id, function(input, output, session) {
      chat_enable_history(
        "chat",
        client,
        options = history_options(
          store = store,
          scope = "browser-1",
          title = NULL
        ),
        session = session
      )
    })
  }

  shiny::testServer(chat_mod, args = list(id = "mod1"), {
    ctrl <- get_session_chat_bookmark_info(
      session,
      "chat.history-controller"
    )

    session$setInputs(chat_history_browser_token = "tok-abc")

    expect_equal(ctrl$partition$chat_id, session$ns("chat"))
    expect_equal(ctrl$partition$scope, "browser-1")

    ctrl$on_response(list())

    expect_equal(
      store$list(conversation_partition(session$ns("chat"), "browser-1"))[[
        1
      ]]$id,
      ctrl$record$id
    )
    expect_length(store$list(conversation_partition("chat", "browser-1")), 0)
  })
})

test_that("deprecated bookmark_on_input warns", {
  skip_if_not_installed("ellmer")
  client <- mock_chat_client()

  expect_warning(
    shiny::testServer(
      function(input, output, session) {
        chat_server("chat", client, bookmark_on_input = TRUE, session = session)
      },
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
      function(input, output, session) {
        chat_server(
          "chat",
          client,
          bookmark_on_response = TRUE,
          session = session
        )
      },
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
  partition <- conversation_partition("test", "user1")
  store$put(partition, old1)
  store$put(partition, old2)

  client <- mock_chat_client()
  controller <- HistoryController$new(
    chat_id = "test",
    client = client,
    options = history_options(store = store, max_store_mb = 1e-6, title = NULL),
    session = shiny::MockShinySession$new()
  )
  controller$partition <- partition

  # Trigger on_response with empty turns (saves a new record, then evicts old
  # ones). The active record alone still exceeds the (tiny) budget, so a
  # once-per-chat_id warning fires too.
  expect_warning(controller$on_response(list()), "exceeds")

  metas <- store$list(partition)
  ids <- vapply(metas, `[[`, character(1L), "id")

  # Both pre-existing conversations should be evicted; new active one preserved
  expect_false(old1$id %in% ids)
  expect_false(old2$id %in% ids)
  expect_true(controller$record$id %in% ids)
})

test_that("evict_if_needed calls list() once and never calls total_size (regression)", {
  # Regression: total_size() used to be re-called (a full-scope sweep) on
  # every eviction iteration. The running total should now come entirely
  # from a single list() call's per-record size_bytes.
  list_calls <- 0
  total_size_calls <- 0
  SpyStore <- R6::R6Class(
    "SpyStore",
    inherit = InMemoryConversationStore,
    public = list(
      list = function(partition) {
        list_calls <<- list_calls + 1
        super$list(partition)
      },
      total_size = function(partition) {
        total_size_calls <<- total_size_calls + 1
        super$total_size(partition)
      }
    )
  )
  store <- SpyStore$new()

  rec1 <- new_conversation_record("oldest")
  rec2 <- new_conversation_record("middle")
  rec3 <- new_conversation_record("newest")
  partition <- conversation_partition("test", "alice")
  store$put(partition, rec1)
  store$put(partition, rec2)
  store$put(partition, rec3)

  controller <- HistoryController$new(
    chat_id = "test",
    client = mock_chat_client(),
    options = history_options(store = store, max_store_mb = 1e-6, title = NULL),
    session = shiny::MockShinySession$new()
  )
  controller$partition <- partition
  controller$record <- rec3

  evict_if_needed <- controller$.__enclos_env__$private$evict_if_needed
  evict_if_needed()

  expect_equal(list_calls, 1)
  expect_equal(total_size_calls, 0)
})

test_that("evict_if_needed warns once (not on every response) when the active conversation alone exceeds the quota", {
  store <- InMemoryConversationStore$new()
  rec <- new_conversation_record("active")
  partition <- conversation_partition("warn-once-test", "user1")
  store$put(partition, rec)

  client <- mock_chat_client()
  controller <- HistoryController$new(
    chat_id = "warn-once-test",
    client = client,
    options = history_options(store = store, max_store_mb = 1e-6, title = NULL),
    session = shiny::MockShinySession$new()
  )
  controller$partition <- partition
  controller$record <- rec

  evict_if_needed <- controller$.__enclos_env__$private$evict_if_needed
  expect_warning(evict_if_needed(), "exceeds")
  # Same chat_id, still over budget: no second warning (cli's .frequency = "once").
  expect_no_warning(evict_if_needed())
})

test_that("HistoryController does not warn when total fits after eviction", {
  store <- InMemoryConversationStore$new()
  client <- mock_chat_client()
  controller <- HistoryController$new(
    chat_id = "test-no-warn",
    client = client,
    options = history_options(store = store, max_store_mb = 10, title = NULL),
    session = shiny::MockShinySession$new()
  )
  controller$partition <- conversation_partition("test-no-warn", "user1")

  expect_no_warning(controller$on_response(list()))
})

test_that("max_store_mb large enough to overflow a 32-bit integer does not produce NA (regression)", {
  # as.integer(2048 * 1024 * 1024) overflows .Machine$integer.max and yields
  # NA, which previously broke the `total <= max_bytes` comparison.
  client <- mock_chat_client()
  controller <- HistoryController$new(
    chat_id = "test",
    client = client,
    options = history_options(
      store = InMemoryConversationStore$new(),
      max_store_mb = 2048,
      title = NULL
    ),
    session = shiny::MockShinySession$new()
  )

  max_bytes <- controller$.__enclos_env__$private$max_store_bytes
  expect_false(is.na(max_bytes))
  expect_equal(max_bytes, 2048 * 1024 * 1024)

  controller$partition <- conversation_partition("test", "user1")
  expect_no_warning(expect_no_error(controller$on_response(list())))
})

test_that("FileConversationStore$total_size() does not overflow a 32-bit integer (regression)", {
  store <- FileConversationStore$new(dir = withr::local_tempdir())
  rec <- new_conversation_record("big")
  partition <- conversation_partition("test", "user1")
  store$put(partition, rec)

  # as.integer(sum(file.size(files))) overflows past ~2GB and returns NA.
  # Stub file.size() to simulate a scope whose files exceed that threshold.
  testthat::local_mocked_bindings(
    file.size = function(...) 3e9,
    .package = "base"
  )

  total <- store$total_size(partition)
  expect_false(is.na(total))
  expect_equal(total, 3e9)
})

test_that("init waits for browser token when session$user is set (browser restore)", {
  # Regression: on Connect (or any authenticated Shiny deployment), session$user
  # is available immediately, so scope_val used to resolve in the first reactive
  # flush — before the browser sends _history_browser_token and _history_current_id
  # (which arrive only after Shiny's initializedPromise resolves). The init
  # observer would fire with current_id = NULL, set initialized = TRUE, and the
  # active conversation would never be restored. The fix requires the browser
  # token before scope resolves in browser/url restore modes.
  skip_if_not_installed("ellmer")

  client <- mock_chat_client()
  session <- shiny::MockShinySession$new()
  session$user <- "testuser"
  store <- InMemoryConversationStore$new()
  rec <- new_conversation_record("Prior conversation")
  store$put(conversation_partition(session$ns("chat"), "testuser"), rec)

  server <- function(input, output, session) {
    chat_enable_history(
      "chat",
      client,
      options = history_options(store = store, title = NULL)
    )
  }

  shiny::testServer(server, session = session, {
    ctrl <- get_session_chat_bookmark_info(session, "chat.history-controller")

    # First flush: browser token not yet sent. The init observer must NOT have
    # fired yet despite session$user being available.
    expect_null(ctrl$record)

    # Simulate the client sending token + current_id in the same microtask
    # (initializedPromise.then() dispatches both atomically).
    session$setInputs(
      chat_history_browser_token = "tok-abc",
      chat_history_current_id = rec$id
    )

    # Init should now have fired and restored the saved conversation.
    expect_equal(ctrl$record$id, rec$id)
  })
})

test_that("set_client() does not re-render the UI or double-fire on_restore (regression)", {
  # Regression: chat_enable_history() was re-run from scratch on every
  # set_client() swap, spinning up a fresh controller/init effect with no
  # equivalent of chat_restore()'s restore_ui = FALSE. The new init effect
  # read the unchanged browser-localStorage current_id, found the
  # already-active conversation, and called replay_ui() (clearing +
  # re-rendering the chat) plus restore_after_first_flush() (re-firing
  # on_restore) a second time -- on every swap, not just an edge case.
  skip_if_not_installed("ellmer")

  client <- mock_chat_client()
  session <- shiny::MockShinySession$new()
  session$user <- "testuser"
  store <- InMemoryConversationStore$new()
  rec <- new_conversation_record("Prior conversation")
  store$put(conversation_partition(session$ns("chat"), "testuser"), rec)

  restore_count <- 0
  mod_ref <- NULL

  server <- function(input, output, session) {
    mod <- chat_server(
      "chat",
      client,
      history = history_options(store = store, title = NULL),
      session = session
    )
    mod$history$on_restore(function(values) {
      restore_count <<- restore_count + 1
      values
    })
    mod_ref <<- mod
    mod
  }

  shiny::testServer(server, session = session, {
    session$setInputs(
      chat_history_browser_token = "tok-abc",
      chat_history_current_id = rec$id
    )
    expect_equal(restore_count, 1)

    mod_ref$set_client(mock_chat_client())

    # Trigger the next flush, where a re-registered restore_after_first_flush()
    # would fire if the swap re-ran the restore path.
    session$setInputs(chat_history_browser_token = "tok-abc")
    expect_equal(restore_count, 1)
  })
})

test_that("HistoryController does not evict when no limit set", {
  store <- InMemoryConversationStore$new()
  old <- new_conversation_record("old")
  partition <- conversation_partition("test", "user1")
  store$put(partition, old)

  client <- mock_chat_client()
  controller <- HistoryController$new(
    chat_id = "test",
    client = client,
    options = history_options(store = store, max_store_mb = NULL, title = NULL),
    session = shiny::MockShinySession$new()
  )
  controller$partition <- partition

  controller$on_response(list())

  expect_length(store$list(partition), 2L) # old + new
})

test_that("HistoryController evict_one removes the record from the store", {
  store <- InMemoryConversationStore$new()
  rec <- new_conversation_record("to evict")
  partition <- conversation_partition("test", "user1")
  store$put(partition, rec)

  client <- mock_chat_client()
  controller <- HistoryController$new(
    chat_id = "test",
    client = client,
    options = history_options(store = store, max_store_mb = NULL, title = NULL),
    session = shiny::MockShinySession$new()
  )
  controller$partition <- partition

  controller$.__enclos_env__$private$evict_one(rec$id)

  expect_null(store$get(partition, rec$id))
})
