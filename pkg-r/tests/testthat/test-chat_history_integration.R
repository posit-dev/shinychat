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

test_that("chat_server() history save returns FALSE before a conversation exists", {
  skip_if_not_installed("ellmer")

  client <- mock_chat_client()
  chat_module <- NULL

  shiny::testServer(
    function(input, output, session) {
      chat_module <<- chat_server(
        "chat",
        client,
        history = TRUE,
        session = session
      )
    },
    {
      expect_identical(chat_module$history$save(), FALSE)
    }
  )
})

test_that("chat_server() history save persists an active conversation", {
  skip_if_not_installed("ellmer")

  client <- mock_chat_client()
  store <- InMemoryConversationStore$new()
  chat_module <- NULL

  shiny::testServer(
    function(input, output, session) {
      chat_module <<- chat_server(
        "chat",
        client,
        history = history_options(
          store = store,
          scope = "test-user",
          title = NULL
        ),
        session = session
      )
    },
    {
      session$setInputs(chat_history_browser_token = "browser-token")
      ctrl <- get_session_chat_bookmark_info(session, "chat.history-controller")
      ctrl$record <- new_conversation_record("Saved conversation")

      expect_identical(chat_module$history$save(), TRUE)
      expect_equal(
        store$get(ctrl$partition, ctrl$record$id)$title,
        "Saved conversation"
      )
    }
  )
})

test_that("chat_server() history save finds a non-default controller", {
  skip_if_not_installed("ellmer")

  client <- mock_chat_client()
  store <- InMemoryConversationStore$new()
  chat_module <- NULL

  shiny::testServer(
    function(input, output, session) {
      chat_module <<- chat_server(
        "mychat",
        client,
        history = history_options(
          store = store,
          scope = "test-user",
          title = NULL
        ),
        session = session
      )
    },
    {
      session$setInputs(mychat_history_browser_token = "browser-token")
      ctrl <- get_session_chat_bookmark_info(
        session,
        "mychat.history-controller"
      )
      ctrl$record <- new_conversation_record("Saved conversation")

      expect_false(is.null(ctrl$partition))
      expect_identical(chat_module$history$save(), TRUE)
      expect_equal(
        store$get(ctrl$partition, ctrl$record$id)$title,
        "Saved conversation"
      )
    }
  )
})

test_that("chat_server() history save returns FALSE when history is disabled", {
  skip_if_not_installed("ellmer")

  client <- mock_chat_client()
  chat_module <- NULL

  shiny::testServer(
    function(input, output, session) {
      chat_module <<- chat_server(
        "chat",
        client,
        history = FALSE,
        session = session
      )
    },
    {
      expect_identical(chat_module$history$save(), FALSE)
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
  # Each conversation directory has 3 files (record.json, turns.jsonl,
  # ui.jsonl), so the stubbed per-file size is summed 3x.
  testthat::local_mocked_bindings(
    file.size = function(...) 3e9,
    .package = "base"
  )

  total <- store$total_size(partition)
  expect_false(is.na(total))
  expect_equal(total, 9e9)
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

test_that("bookmark startup restores history state after activating conversation", {
  skip_if_not_installed("ellmer")

  old_bookmark_store <- shiny::getShinyOption("bookmarkStore", NULL)
  withr::defer(shiny::shinyOptions(bookmarkStore = old_bookmark_store))

  client <- mock_chat_client()
  session <- shiny::MockShinySession$new()
  store <- InMemoryConversationStore$new()
  record <- new_conversation_record("Prior conversation")
  record$values <- list(marker = "from-history")
  store$put(
    conversation_partition(session$ns("chat"), "test-user"),
    record
  )
  session$restoreContext <- list(
    active = TRUE,
    values = list(chat_history_conversation_id = record$id)
  )

  restored_marker <- NULL
  observed_id <- NULL
  server <- function(input, output, session) {
    shiny::shinyOptions(bookmarkStore = "server")
    chat_enable_history(
      "chat",
      client,
      on_restore = function(values) {
        restored_marker <<- values$marker
        ctrl <- get_session_chat_bookmark_info(
          session,
          "chat.history-controller"
        )
        observed_id <<- ctrl$record$id
      },
      options = history_options(
        restore_mode = "bookmark",
        store = store,
        scope = "test-user",
        title = NULL
      )
    )
  }

  shiny::testServer(server, session = session, {
    session$flushReact()

    expect_identical(restored_marker, "from-history")
    expect_identical(observed_id, record$id)
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

test_that("set_client() seeds ui_offset from the restored record so a post-swap turn does not duplicate prior UI (regression)", {
  # Regression: init_effect()'s restore_ui = FALSE branch (used by
  # set_client() on every LLM-client/model swap) left ui_offset at its
  # HistoryController$new() default of 0 instead of seeding it from the
  # record being restored. The browser still holds the full historical
  # transcript, so on the next real turn after a swap, extend_record_linear()
  # treated the *entire* transcript as "new" ui and re-attached it onto the
  # newly created node, duplicating every previously-stored UI message.
  skip_if_not_installed("ellmer")

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

  client <- mock_chat_client()
  session <- shiny::MockShinySession$new()
  session$user <- "testuser"

  store <- InMemoryConversationStore$new()
  rec <- new_conversation_record("Prior conversation")
  rec$nodes <- list(
    n_0001 = list(
      parent = NULL,
      children = list(),
      turns = list(make_turn("user", "hi")),
      ui = list(make_ui_message("user", "hi"))
    ),
    n_0002 = list(
      parent = "n_0001",
      children = list(),
      turns = list(make_turn("assistant", "hello")),
      ui = list(make_ui_message("assistant", "hello"))
    )
  )
  rec$current_leaf <- "n_0002"
  store$put(conversation_partition(session$ns("chat"), "testuser"), rec)

  mod_ref <- NULL

  server <- function(input, output, session) {
    mod <- chat_server(
      "chat",
      client,
      history = history_options(store = store, title = NULL),
      session = session
    )
    mod_ref <<- mod
    mod
  }

  shiny::testServer(server, session = session, {
    session$setInputs(
      chat_history_browser_token = "tok-abc",
      chat_history_current_id = rec$id
    )

    new_client <- mock_chat_client()
    mod_ref$set_client(new_client)

    # Trigger the next flush so the new controller's init effect (which
    # depends on the browser token) actually runs.
    session$setInputs(chat_history_browser_token = "tok-abc")

    ctrl <- get_session_chat_bookmark_info(session, "chat.history-controller")
    expect_equal(ctrl$ui_offset, 2)

    # Simulate a new turn arriving after the swap: on_response() receives the
    # FULL recorded-turns list (as chat_history_on_response() would derive
    # from the live client), and the browser reports the FULL historical
    # `chat_messages` transcript (as a real client would) plus the new
    # message -- not just the new tail.
    session$setInputs(
      chat_messages = list(
        make_ui_message("user", "hi"),
        make_ui_message("assistant", "hello"),
        make_ui_message("user", "again")
      )
    )

    ctrl$on_response(
      list(
        make_turn("user", "hi"),
        make_turn("assistant", "hello"),
        make_turn("user", "again")
      )
    )

    reloaded <- store$get(
      conversation_partition(session$ns("chat"), "testuser"),
      ctrl$record$id
    )
    expect_equal(record_ui_count(reloaded), 3)

    ui_texts <- unlist(
      lapply(
        record_path_node_ids(reloaded),
        function(node_id) {
          vapply(
            reloaded$nodes[[node_id]]$ui,
            function(m) m$segments[[1]]$content,
            character(1)
          )
        }
      )
    )
    expect_equal(ui_texts, c("hi", "hello", "again"))
  })
})

test_that("the client's `_messages` echo drives the save; UI is server-derived from turns (P4)", {
  # Regression for the save-timing bug: the save must be triggered by the
  # browser echoing its rendered `_messages` snapshot, not by server-side
  # stream completion. If it fired on completion, the just-finished assistant
  # message would not yet be in the client's report, so the save would
  # misattribute it to the wrong round.
  #
  # Per P4: the stored UI is now server-derived from turns, not from the
  # client snapshot. The client's displayed/transformed form ("hello
  # (displayed)") is NOT preserved — the turn text ("hello") is. The client
  # snapshot remains the save trigger and the bookkeeping source, but not the
  # persisted UI source.
  skip_if_not_installed("ellmer")

  make_turn <- function(role, text) {
    list(
      class = if (role == "user") {
        "ellmer::UserTurn"
      } else {
        "ellmer::AssistantTurn"
      },
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

  client <- mock_chat_client()
  session <- shiny::MockShinySession$new()
  store <- InMemoryConversationStore$new()

  server <- function(input, output, session) {
    chat_server(
      "chat",
      client,
      history = history_options(
        store = store,
        scope = "browser-1",
        title = NULL
      ),
      session = session
    )
  }

  shiny::testServer(server, session = session, {
    session$setInputs(chat_history_browser_token = "tok-abc")

    ctrl <- get_session_chat_bookmark_info(session, "chat.history-controller")
    expect_false(is.null(ctrl$partition))

    # A response has just completed server-side: the live client holds both
    # turns, and the assistant reply as recorded is the plain "hello".
    set_turns_recorded(
      client,
      list(make_turn("user", "hi"), make_turn("assistant", "hello"))
    )

    # The browser has not yet reported the finished assistant message -- its
    # last reported message is still the user's -- so no save should fire.
    session$setInputs(chat_messages = list(make_ui_message("user", "hi")))
    expect_null(ctrl$record)

    # The browser now echoes its rendered transcript, in which the displayed
    # assistant message was transformed for display (differs from the turn
    # text). The observer fires and the save records this displayed form.
    session$setInputs(
      chat_messages = list(
        make_ui_message("user", "hi"),
        make_ui_message("assistant", "hello (displayed)")
      )
    )

    expect_false(is.null(ctrl$record))

    saved <- store$get(
      conversation_partition(session$ns("chat"), "browser-1"),
      ctrl$record$id
    )
    node_ids <- record_path_node_ids(saved)
    last_ui <- saved$nodes[[node_ids[[length(node_ids)]]]]$ui
    expect_equal(last_ui[[1]]$role, "assistant")
    # Per P4: the stored UI is server-derived from turns, not from the
    # client's displayed form. The turn text is "hello", not "hello
    # (displayed)".
    expect_equal(last_ui[[1]]$segments[[1]]$content, "hello")
  })
})

test_that("editing a message after the first forks at the correct node even when the client's UI echo lags the assistant turn (regression)", {
  # Regression: the history save trigger used to fire as soon as the
  # server-side stream finished (chained directly onto chat_append_stream()'s
  # promise), before the browser had echoed the just-completed assistant
  # reply back through `<chat_id>_messages`. Given that lag,
  # extend_record_linear() attached the *previous* round's late-arriving
  # assistant ui message to the *current* round's fallback node, permanently
  # leaving one node's `ui` unset. record_node_id_for_message_index() counts
  # by `length(node$ui)`, so that unset node silently undercounted by one --
  # shifting every later handle_edit()/handle_navigate() message_index lookup
  # one node too far. In particular, editing any message after the first
  # forked one node too late, leaving the pre-edit message on the path
  # alongside whatever got resubmitted in its place (a visible duplicate).
  skip_if_not_installed("ellmer")

  make_live_turn <- function(role, text) {
    content <- ellmer::ContentText(text = text)
    if (role == "user") {
      ellmer::UserTurn(contents = list(content))
    } else {
      ellmer::AssistantTurn(contents = list(content))
    }
  }
  make_ui_message <- function(role, text) {
    list(
      role = role,
      segments = list(list(content = text, content_type = "markdown"))
    )
  }

  client <- mock_chat_client()
  session <- shiny::MockShinySession$new()
  session$user <- "testuser"
  store <- InMemoryConversationStore$new()

  server <- function(input, output, session) {
    chat_server(
      "chat",
      client,
      history = history_options(
        store = store,
        title = NULL,
        restore_mode = "none"
      ),
      session = session
    )
  }

  shiny::testServer(server, session = session, {
    # Round 1: user "one" -> assistant "R1". The browser's echo of
    # `chat_messages` necessarily lags the server-side stream completion by a
    # round trip: it reports only "one" first, then catches up to include
    # "R1" once the client has rendered and re-echoed it.
    client$set_turns(
      list(
        make_live_turn("user", "one"),
        make_live_turn("assistant", "R1")
      )
    )
    session$setInputs(chat_messages = list(make_ui_message("user", "one")))
    session$setInputs(
      chat_messages = list(
        make_ui_message("user", "one"),
        make_ui_message("assistant", "R1")
      )
    )

    ctrl <- get_session_chat_bookmark_info(session, "chat.history-controller")
    expect_equal(length(ctrl$record$nodes), 2)

    # Round 2: user "two" -> assistant "R2", same lag pattern.
    client$set_turns(
      list(
        make_live_turn("user", "one"),
        make_live_turn("assistant", "R1"),
        make_live_turn("user", "two"),
        make_live_turn("assistant", "R2")
      )
    )
    session$setInputs(
      chat_messages = list(
        make_ui_message("user", "one"),
        make_ui_message("assistant", "R1"),
        make_ui_message("user", "two")
      )
    )
    session$setInputs(
      chat_messages = list(
        make_ui_message("user", "one"),
        make_ui_message("assistant", "R1"),
        make_ui_message("user", "two"),
        make_ui_message("assistant", "R2")
      )
    )
    expect_equal(length(ctrl$record$nodes), 4)

    # Edit the second user message ("two", ui message index 2). The fork
    # point must land on "R1"'s node (n_0002) -- excluding "two" and "R2"
    # entirely -- not one node later, which would keep the original "two"
    # message on the path alongside whatever gets resubmitted in its place.
    session$setInputs(
      chat_message_edit = list(
        index = 2L,
        content = "two EDITED",
        attachments = list()
      )
    )

    expect_equal(ctrl$record$current_leaf, "n_0002")
  })
})

test_that("file-backed turns survive restore, continuation, and a second restore", {
  skip_if_not_installed("ellmer")

  make_live_turn <- function(role, text) {
    content <- ellmer::ContentText(text = text)
    if (role == "user") {
      ellmer::UserTurn(contents = list(content))
    } else {
      ellmer::AssistantTurn(
        contents = list(content),
        json = list(1, "two")
      )
    }
  }
  make_ui_message <- function(role, text) {
    list(
      role = role,
      segments = list(list(content = text, content_type = "markdown"))
    )
  }

  dir <- withr::local_tempdir()

  client <- mock_chat_client()
  session <- shiny::MockShinySession$new()
  session$user <- "testuser"
  store <- FileConversationStore$new(dir = dir)

  server <- function(input, output, session) {
    chat_server(
      "chat",
      client,
      history = history_options(store = store, title = NULL),
      session = session
    )
  }

  saved_id <- NULL
  shiny::testServer(server, session = session, {
    session$setInputs(chat_history_browser_token = "tok-abc")

    client$set_turns(
      list(
        make_live_turn("user", "hi"),
        make_live_turn("assistant", "hello")
      )
    )
    session$setInputs(
      chat_messages = list(
        make_ui_message("user", "hi"),
        make_ui_message("assistant", "hello")
      )
    )

    ctrl <- get_session_chat_bookmark_info(session, "chat.history-controller")
    saved_id <<- ctrl$record$id
  })

  new_client <- mock_chat_client()
  new_session <- shiny::MockShinySession$new()
  new_session$user <- "testuser"
  restarted_store <- FileConversationStore$new(dir = dir)

  new_server <- function(input, output, session) {
    chat_server(
      "chat",
      new_client,
      history = history_options(store = restarted_store, title = NULL),
      session = session
    )
  }

  shiny::testServer(new_server, session = new_session, {
    expect_no_error(
      session$setInputs(
        chat_history_browser_token = "tok-abc",
        chat_history_current_id = saved_id
      )
    )

    restored_turns <- new_client$get_turns()
    expect_length(restored_turns, 2)
    expect_true(S7::S7_inherits(restored_turns[[1]], ellmer::UserTurn))
    expect_equal(restored_turns[[1]]@contents[[1]]@text, "hi")
    expect_true(S7::S7_inherits(restored_turns[[2]], ellmer::AssistantTurn))
    expect_equal(restored_turns[[2]]@contents[[1]]@text, "hello")
    expect_identical(restored_turns[[2]]@json, list(1, "two"))
    expect_identical(restored_turns[[2]]@tokens, rep(NA_real_, 3))
    expect_identical(restored_turns[[2]]@cost, NA_real_)
    expect_identical(restored_turns[[2]]@duration, NA_real_)
    expect_identical(restored_turns[[2]]@finish_reason, NA_character_)

    session$setInputs(
      chat_messages = list(
        make_ui_message("user", "hi"),
        make_ui_message("assistant", "hello")
      )
    )

    new_client$set_turns(
      c(
        restored_turns,
        list(
          make_live_turn("user", "again"),
          make_live_turn("assistant", "welcome back")
        )
      )
    )
    session$setInputs(
      chat_messages = list(
        make_ui_message("user", "hi"),
        make_ui_message("assistant", "hello"),
        make_ui_message("user", "again"),
        make_ui_message("assistant", "welcome back")
      )
    )
  })

  final_client <- mock_chat_client()
  final_session <- shiny::MockShinySession$new()
  final_session$user <- "testuser"
  final_store <- FileConversationStore$new(dir = dir)

  final_server <- function(input, output, session) {
    chat_server(
      "chat",
      final_client,
      history = history_options(store = final_store, title = NULL),
      session = session
    )
  }

  shiny::testServer(final_server, session = final_session, {
    session$setInputs(
      chat_history_browser_token = "tok-abc",
      chat_history_current_id = saved_id
    )

    restored_turns <- final_client$get_turns()
    expect_length(restored_turns, 4)
    expect_equal(
      vapply(
        restored_turns,
        function(turn) turn@contents[[1]]@text,
        character(1)
      ),
      c("hi", "hello", "again", "welcome back")
    )
    expect_identical(restored_turns[[2]]@json, list(1, "two"))
    expect_identical(restored_turns[[4]]@json, list(1, "two"))
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
