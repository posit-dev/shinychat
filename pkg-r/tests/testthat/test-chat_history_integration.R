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

test_that("chat_server(history = FALSE) registers a transcript", {
  client <- mock_chat_client()

  shiny::testServer(
    function(input, output, session) {
      chat_server("chat", client, history = FALSE, session = session)
    },
    {
      expect_false(is.null(get_chat_transcript(session, "chat")))
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

test_that("chat_enable_history() registers a transcript", {
  client <- mock_chat_client()
  session <- shiny::MockShinySession$new()
  store <- InMemoryConversationStore$new()

  chat_enable_history(
    "chat",
    client,
    options = history_options(
      store = store,
      restore_mode = "none",
      title = NULL
    ),
    session = session
  )

  expect_false(is.null(get_chat_transcript(session, "chat")))
})

test_that("chat_server() followed by chat_enable_history() reuses one transcript", {
  client <- mock_chat_client()
  store <- InMemoryConversationStore$new()

  shiny::testServer(
    function(input, output, session) {
      chat_server("chat", client, history = FALSE, session = session)
    },
    {
      before <- get_chat_transcript(session, "chat")
      chat_enable_history(
        "chat",
        client,
        options = history_options(
          store = store,
          restore_mode = "none",
          title = NULL
        ),
        session = session
      )
      expect_identical(get_chat_transcript(session, "chat"), before)
    }
  )
})

test_that("chat_server() stores raw user input before the stream reads it", {
  local_mocked_bindings(
    chat_append = function(...) invisible(NULL),
    send_chat_action = function(...) invisible(NULL)
  )
  attachment <- list(
    mime = "text/plain",
    data_url = "data:text/plain;base64,bm90ZXM=",
    name = "notes.txt",
    size = 5
  )
  input_value <- user_input_contents(
    list(text = "Summarize", attachments = list(attachment))
  )
  state_during_stream <- NULL
  stream_args <- NULL
  active_session <- NULL
  mod_ref <- NULL
  client <- structure(
    list(
      stream_async = function(...) {
        state_during_stream <<- get_chat_transcript(
          active_session,
          "chat"
        )$read()
        stream_args <<- rlang::list2(...)
        NULL
      },
      last_turn = function() NULL
    ),
    class = "Chat"
  )

  shiny::testServer(
    function(input, output, session) {
      active_session <<- session
      mod_ref <<- chat_server(
        "chat",
        client,
        history = FALSE,
        session = session
      )
    },
    {
      session$setInputs(chat_user_input = input_value)
      deadline <- Sys.time() + 2
      while (
        (is.null(stream_args) || identical(mod_ref$status(), "streaming")) &&
          Sys.time() < deadline
      ) {
        later::run_now(0.05)
        session$flushReact()
      }

      expect_identical(stream_args[[1]], input_value[[1]])
      expect_identical(stream_args[[2]], input_value[[2]])
      expect_identical(
        state_during_stream,
        list(
          list(
            role = "user",
            segments = list(
              list(content = "Summarize", content_type = "markdown")
            ),
            attachments = list(attachment)
          )
        )
      )
    }
  )
})

test_that("chat_server() chains one history branch to each managed response", {
  history_calls <- 0L
  managed_promise <- NULL
  history_promise <- NULL
  local_mocked_bindings(
    chat_append = function(...) {
      managed_promise <<- promises::promise_resolve("complete")
      managed_promise
    },
    chat_history_on_response = function(id, stream_promise, session) {
      history_calls <<- history_calls + 1L
      history_promise <<- stream_promise
      expect_equal(id, "chat")
      stream_promise
    },
    send_chat_action = function(...) invisible(NULL)
  )
  client <- structure(
    list(
      stream_async = function(...) "response",
      last_turn = function() NULL
    ),
    class = "Chat"
  )
  mod_ref <- NULL

  shiny::testServer(
    function(input, output, session) {
      mod_ref <<- chat_server(
        "chat",
        client,
        history = FALSE,
        session = session
      )
    },
    {
      session$setInputs(
        chat_user_input = user_input_contents(list(text = "Hi"))
      )
      deadline <- Sys.time() + 2
      while (
        identical(mod_ref$status(), "streaming") &&
          Sys.time() < deadline
      ) {
        later::run_now(0.05)
        session$flushReact()
      }
      later::run_now(0.1)
      session$flushReact()

      expect_equal(history_calls, 1L)
      expect_promise(history_promise)
      expect_promise(managed_promise)
      expect_equal(mod_ref$status(), "idle")
    }
  )
})

test_that("chat_history_on_response() saves fulfilled and rejected settlements", {
  session <- shiny::MockShinySession$new()
  saved <- 0L
  client <- mock_chat_client()
  controller <- new.env(parent = emptyenv())
  controller$get_client <- function() client
  controller$on_response <- function(recorded_turns) {
    saved <<- saved + 1L
    invisible(NULL)
  }
  set_session_chat_bookmark_info(
    session,
    "chat.history-controller",
    controller
  )

  fulfilled <- promises::promise_resolve("complete")
  expect_identical(
    chat_history_on_response(
      id = "chat",
      stream_promise = fulfilled,
      session = session
    ),
    fulfilled
  )
  expect_equal(sync(fulfilled), "complete")
  later::run_now(0.1)

  rejected <- promises::promise_reject(rlang::error_cnd("cancelled"))
  expect_identical(
    chat_history_on_response("chat", rejected, session),
    rejected
  )
  promises::catch(rejected, function(reason) NULL)
  later::run_now(0.1)

  expect_equal(saved, 2L)
})

managed_stream_client <- function(stream_factory) {
  client <- mock_chat_client()
  client$stream_async <- function(..., stream, controller) {
    input <- rlang::list2(...)[[1L]]
    client$set_turns(list(ellmer::UserTurn(input)))
    stream_factory(client, controller)
  }
  client
}

wait_for_condition <- function(condition, session) {
  deadline <- Sys.time() + 2
  while (!condition() && Sys.time() < deadline) {
    later::run_now(0.05)
    session$flushReact()
  }
  expect_true(condition())
  later::run_now(0.1)
  session$flushReact()
}

recorded_ui_messages <- function(record) {
  unlist(
    lapply(record_path_node_ids(record), function(node_id) {
      record$nodes[[node_id]]$ui %||% list()
    }),
    recursive = FALSE
  )
}

test_that("synchronous stream creation failure settles user history and preserves its error", {
  put_calls <- 0L
  attempted_record <- NULL
  FailingStore <- R6::R6Class(
    "SynchronousCreationFailingStore",
    inherit = InMemoryConversationStore,
    public = list(
      put = function(partition, record) {
        put_calls <<- put_calls + 1L
        attempted_record <<- record
        rlang::abort("history save failed", class = "history_save_error")
      }
    )
  )
  marker <- new.env(parent = emptyenv())
  original <- structure(
    list(message = "synchronous model failure", call = NULL, marker = marker),
    class = c("creation_original_error", "error", "condition")
  )
  client <- mock_chat_client()
  client$stream_async <- function(..., stream, controller) {
    input <- rlang::list2(...)[[1L]]
    client$set_turns(list(ellmer::UserTurn(input)))
    stop(original)
  }
  warnings <- list()
  store <- FailingStore$new()
  local_mocked_bindings(
    send_chat_action = function(...) invisible(NULL)
  )

  withCallingHandlers(
    shiny::testServer(
      function(input, output, session) {
        chat_server(
          "chat",
          client,
          history = history_options(
            store = store,
            scope = "test-user",
            restore_mode = "none",
            title = NULL
          ),
          session = session
        )
      },
      {
        session$setInputs(chat_user_input = "Hello")
        wait_for_condition(function() put_calls == 1L, session)
      }
    ),
    warning = function(warning) {
      warnings[[length(warnings) + 1L]] <<- warning
      invokeRestart("muffleWarning")
    }
  )

  expect_equal(put_calls, 1L)
  expect_equal(attempted_record$response_count, 1L)
  expect_identical(
    recorded_ui_messages(attempted_record),
    list(
      list(
        role = "user",
        segments = list(list(content = "Hello", content_type = "markdown"))
      )
    )
  )
  expect_true(
    any(
      vapply(
        warnings,
        function(warning) {
          grepl(
            "Could not save conversation",
            conditionMessage(warning),
            fixed = TRUE
          )
        },
        logical(1)
      )
    )
  )
  task_warnings <- Filter(
    function(warning) {
      grepl("ExtendedTask", conditionMessage(warning), fixed = TRUE)
    },
    warnings
  )
  expect_length(task_warnings, 1L)
  task_error <- task_warnings[[1L]]$parent
  expect_s3_class(task_error, "creation_original_error")
  expect_identical(task_error$marker, marker)
})

test_that("rejected stream creation promise settles canonical user history once", {
  put_calls <- 0L
  RecordingStore <- R6::R6Class(
    "RejectedCreationRecordingStore",
    inherit = InMemoryConversationStore,
    public = list(
      put = function(partition, record) {
        put_calls <<- put_calls + 1L
        super$put(partition, record)
      }
    )
  )
  marker <- new.env(parent = emptyenv())
  original <- structure(
    list(message = "rejected model creation", call = NULL, marker = marker),
    class = c("creation_original_error", "error", "condition")
  )
  client <- mock_chat_client()
  client$stream_async <- function(..., stream, controller) {
    input <- rlang::list2(...)[[1L]]
    client$set_turns(list(ellmer::UserTurn(input)))
    promises::promise_reject(original)
  }
  warnings <- list()
  controller <- NULL
  store <- RecordingStore$new()
  local_mocked_bindings(
    send_chat_action = function(...) invisible(NULL)
  )

  withCallingHandlers(
    shiny::testServer(
      function(input, output, session) {
        chat_server(
          "chat",
          client,
          history = history_options(
            store = store,
            scope = "test-user",
            restore_mode = "none",
            title = NULL
          ),
          session = session
        )
        controller <<- get_session_chat_bookmark_info(
          session,
          "chat.history-controller"
        )
      },
      {
        session$setInputs(chat_user_input = "Hello")
        wait_for_condition(function() put_calls == 1L, session)
      }
    ),
    warning = function(warning) {
      warnings[[length(warnings) + 1L]] <<- warning
      invokeRestart("muffleWarning")
    }
  )

  expect_equal(put_calls, 1L)
  expect_equal(controller$record$response_count, 1L)
  expect_identical(
    recorded_ui_messages(controller$record),
    list(
      list(
        role = "user",
        segments = list(list(content = "Hello", content_type = "markdown"))
      )
    )
  )
  task_warnings <- Filter(
    function(warning) {
      grepl("ExtendedTask", conditionMessage(warning), fixed = TRUE)
    },
    warnings
  )
  expect_length(task_warnings, 1L)
  task_error <- task_warnings[[1L]]$parent
  expect_s3_class(task_error, "creation_original_error")
  expect_identical(task_error$marker, marker)
})

test_that("cancelled managed streams save once after transcript settlement", {
  release <- NULL
  released <- promises::promise(function(resolve, reject) {
    release <<- resolve
  })
  put_calls <- 0L
  transcript_at_put <- NULL
  active_session <- NULL
  RecordingStore <- R6::R6Class(
    "CancelledManagedRecordingStore",
    inherit = InMemoryConversationStore,
    public = list(
      put = function(partition, record) {
        put_calls <<- put_calls + 1L
        transcript_at_put <<- get_chat_transcript(
          active_session,
          "chat"
        )$read()
        super$put(partition, record)
      }
    )
  )
  store <- RecordingStore$new()
  client <- managed_stream_client(function(client, controller) {
    coro::async_generator(function() {
      yield("partial")
      coro::await(released)
      if (controller$cancelled) {
        client$set_turns(
          c(
            client$get_turns(),
            list(ellmer::AssistantPartialTurn("partial", reason = "cancelled"))
          )
        )
        return(coro::exhausted())
      }
      yield("late")
    })()
  })
  mod_ref <- NULL
  local_mocked_bindings(
    send_chat_action = function(...) invisible(NULL)
  )

  shiny::testServer(
    function(input, output, session) {
      active_session <<- session
      mod_ref <<- chat_server(
        "chat",
        client,
        history = history_options(
          store = store,
          scope = "test-user",
          restore_mode = "none",
          title = NULL
        ),
        session = session
      )
    },
    {
      session$setInputs(chat_user_input = "Hello")
      wait_for_condition(
        function() identical(mod_ref$status(), "streaming"),
        session
      )
      session$setInputs(chat_cancel = 1)
      release(NULL)
      wait_for_condition(function() put_calls == 1L, session)

      expect_equal(put_calls, 1L)
      expect_identical(
        transcript_at_put,
        list(
          list(
            role = "user",
            segments = list(
              list(content = "Hello", content_type = "markdown")
            )
          ),
          list(
            role = "assistant",
            segments = list(
              list(content = "partial", content_type = "markdown")
            )
          )
        )
      )
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

test_that("errored managed streams save the sanitized settled transcript once", {
  withr::local_options(shiny.sanitize.errors = TRUE)
  put_calls <- 0L
  saved_record <- NULL
  transcript_at_put <- NULL
  active_session <- NULL
  RecordingStore <- R6::R6Class(
    "ErroredManagedRecordingStore",
    inherit = InMemoryConversationStore,
    public = list(
      put = function(partition, record) {
        put_calls <<- put_calls + 1L
        saved_record <<- rlang::duplicate(record, shallow = FALSE)
        transcript_at_put <<- get_chat_transcript(
          active_session,
          "chat"
        )$read()
        super$put(partition, record)
      }
    )
  )
  store <- RecordingStore$new()
  original <- rlang::error_cnd("secret model failure")
  client <- managed_stream_client(function(client, controller) {
    coro::async_generator(function() {
      yield("partial")
      client$set_turns(
        c(
          client$get_turns(),
          list(ellmer::AssistantPartialTurn("partial", reason = "error"))
        )
      )
      stop(original)
    })()
  })
  mod_ref <- NULL
  local_mocked_bindings(
    send_chat_action = function(...) invisible(NULL)
  )

  withCallingHandlers(
    shiny::testServer(
      function(input, output, session) {
        active_session <<- session
        mod_ref <<- chat_server(
          "chat",
          client,
          history = history_options(
            store = store,
            scope = "test-user",
            restore_mode = "none",
            title = NULL
          ),
          session = session
        )
      },
      {
        session$setInputs(chat_user_input = "Hello")
        wait_for_condition(function() put_calls == 1L, session)
      }
    ),
    warning = function(warning) {
      invokeRestart("muffleWarning")
    }
  )

  sanitized <- paste0(
    "partial\n\n**An error occurred. ",
    "Please try again or contact the app author.**"
  )
  expect_equal(put_calls, 1L)
  expect_identical(
    transcript_at_put[[2L]]$segments[[1L]]$content,
    sanitized
  )
  expect_identical(
    recorded_ui_messages(saved_record)[[2L]]$segments[[1L]]$content,
    sanitized
  )
})

test_that("history failure cannot replace a managed stream error", {
  put_calls <- 0L
  FailingStore <- R6::R6Class(
    "FailingManagedResponseStore",
    inherit = InMemoryConversationStore,
    public = list(
      put = function(partition, record) {
        put_calls <<- put_calls + 1L
        rlang::abort("history save failed", class = "history_save_error")
      }
    )
  )
  marker <- new.env(parent = emptyenv())
  original <- structure(
    list(message = "original model failure", call = NULL, marker = marker),
    class = c("model_original_error", "error", "condition")
  )
  client <- managed_stream_client(function(client, controller) {
    coro::async_generator(function() {
      yield("partial")
      client$set_turns(
        c(
          client$get_turns(),
          list(ellmer::AssistantPartialTurn("partial", reason = "error"))
        )
      )
      stop(original)
    })()
  })
  warnings <- list()
  mod_ref <- NULL
  store <- FailingStore$new()
  local_mocked_bindings(
    send_chat_action = function(...) invisible(NULL)
  )

  withCallingHandlers(
    shiny::testServer(
      function(input, output, session) {
        mod_ref <<- chat_server(
          "chat",
          client,
          history = history_options(
            store = store,
            scope = "test-user",
            restore_mode = "none",
            title = NULL
          ),
          session = session
        )
      },
      {
        session$setInputs(chat_user_input = "Hello")
        wait_for_condition(function() put_calls == 1L, session)
      }
    ),
    warning = function(warning) {
      warnings[[length(warnings) + 1L]] <<- warning
      invokeRestart("muffleWarning")
    }
  )

  expect_equal(put_calls, 1L)
  task_warnings <- Filter(
    function(warning) {
      grepl("ExtendedTask", conditionMessage(warning), fixed = TRUE)
    },
    warnings
  )
  expect_length(task_warnings, 1L)
  task_error <- task_warnings[[1L]]$parent
  expect_s3_class(task_error, "model_original_error")
  expect_s3_class(task_error, "shiny.silent.error")
  expect_identical(task_error$marker, marker)
  expect_identical(conditionMessage(task_error), "original model failure")
})

test_that("standalone streams update the transcript without history responses", {
  session <- shiny::MockShinySession$new()
  client <- mock_chat_client()
  store <- InMemoryConversationStore$new()
  chat_enable_history(
    "chat",
    client,
    options = history_options(
      store = store,
      scope = "browser-1",
      restore_mode = "none",
      title = NULL
    ),
    session = session
  )
  stream <- coro::generator(function() {
    yield("standalone")
  })

  sync(chat_append_stream("chat", stream(), session = session))

  controller <- get_session_chat_bookmark_info(
    session,
    "chat.history-controller"
  )
  expect_null(controller$record)
  expect_equal(
    get_chat_transcript(session, "chat")$read()[[1L]]$segments[[1L]]$content,
    "standalone"
  )
})

test_that("standalone failed streams do not save a history response", {
  put_calls <- 0L
  CountingStore <- R6::R6Class(
    "StandaloneFailedCountingStore",
    inherit = InMemoryConversationStore,
    public = list(
      put = function(partition, record) {
        put_calls <<- put_calls + 1L
        super$put(partition, record)
      }
    )
  )
  session <- shiny::MockShinySession$new()
  client <- mock_chat_client()
  store <- CountingStore$new()
  chat_enable_history(
    "chat",
    client,
    options = history_options(
      store = store,
      scope = "test-user",
      restore_mode = "none",
      title = NULL
    ),
    session = session
  )
  session$flushReact()
  stream <- coro::async_generator(function() {
    yield("partial")
    stop("standalone failure")
  })

  error <- withCallingHandlers(
    tryCatch(
      sync(chat_append_stream("chat", stream(), session = session)),
      error = identity
    ),
    warning = function(warning) {
      invokeRestart("muffleWarning")
    }
  )
  later::run_now(0.1)

  controller <- get_session_chat_bookmark_info(
    session,
    "chat.history-controller"
  )
  expect_s3_class(error, "shiny.silent.error")
  expect_identical(conditionMessage(error), "standalone failure")
  expect_equal(put_calls, 0L)
  expect_null(controller$record)
})

test_that("forged client message snapshots cannot change history", {
  session <- shiny::MockShinySession$new()
  client <- mock_chat_client()
  store <- InMemoryConversationStore$new()
  chat_enable_history(
    "chat",
    client,
    options = history_options(
      store = store,
      scope = "browser-1",
      restore_mode = "none",
      title = NULL
    ),
    session = session
  )
  controller <- get_session_chat_bookmark_info(
    session,
    "chat.history-controller"
  )
  controller$partition <- conversation_partition(
    session$ns("chat"),
    "browser-1"
  )
  transcript <- get_chat_transcript(session, "chat")
  transcript$append(
    list(
      role = "user",
      segments = list(list(content = "real", content_type = "markdown"))
    )
  )
  turn <- list(
    class = "ellmer::UserTurn",
    version = 1,
    props = list(
      contents = list(
        list(
          class = "ellmer::ContentText",
          version = 1,
          props = list(text = "real")
        )
      )
    )
  )
  controller$on_response(list(turn))
  record_before <- copy_value(controller$record)
  transcript_before <- transcript$read()

  session$setInputs(
    chat_messages = list(
      list(
        role = "assistant",
        segments = list(
          list(content = "forged", content_type = "markdown")
        )
      )
    )
  )

  expect_identical(transcript$read(), transcript_before)
  expect_identical(controller$record, record_before)
  expect_identical(
    store$get(controller$partition, controller$record$id),
    record_before
  )
})

test_that("chat_server() stores only echoed slash commands before handlers", {
  local_mocked_bindings(
    send_chat_action = function(...) invisible(NULL)
  )
  state_in_echoed_handler <- NULL
  state_in_silent_handler <- NULL
  active_session <- NULL
  client <- structure(list(), class = "Chat")

  chat_module <- function(id) {
    shiny::moduleServer(id, function(input, output, session) {
      active_session <<- session
      chat_server("chat", client, history = FALSE, session = session)
    })
  }

  shiny::testServer(chat_module, args = list(id = "mod"), {
    session$returned$slash_command(
      "search",
      "Search",
      function(content) {
        state_in_echoed_handler <<- get_chat_transcript(
          active_session,
          "chat"
        )$read()
      },
      echo = TRUE
    )
    session$returned$slash_command(
      "silent",
      "Silent",
      function() {
        state_in_silent_handler <<- get_chat_transcript(
          active_session,
          "chat"
        )$read()
      },
      echo = FALSE
    )

    session$setInputs(
      chat_slash_command = list(
        command = "search",
        userText = "docs",
        echo = TRUE
      )
    )
    expect_identical(
      state_in_echoed_handler,
      list(
        list(
          role = "user",
          segments = list(
            list(content = "/search docs", content_type = "markdown")
          )
        )
      )
    )

    session$setInputs(
      chat_slash_command = list(
        command = "silent",
        userText = "",
        echo = FALSE
      )
    )
    expect_identical(state_in_silent_handler, state_in_echoed_handler)
  })
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

test_that("set_client() seeds transcript_offset from the restored record so a post-swap turn does not duplicate prior UI (regression)", {
  # Regression: init_effect()'s restore_ui = FALSE branch (used by
  # set_client() on every LLM-client/model swap) left transcript_offset at its
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
      children = list("n_0002"),
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
    expect_equal(ctrl$transcript_offset, 2)

    get_chat_transcript(session, "chat")$append(
      make_ui_message("user", "again")
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

test_that("the settled transcript preserves transformed assistant UI", {
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

    set_turns_recorded(
      client,
      list(make_turn("user", "hi"), make_turn("assistant", "hello"))
    )
    get_chat_transcript(session, "chat")$replace(
      list(
        make_ui_message("user", "hi"),
        make_ui_message("assistant", "hello (displayed)")
      )
    )
    ctrl$on_response(get_turns_recorded(client))

    saved <- store$get(
      conversation_partition(session$ns("chat"), "browser-1"),
      ctrl$record$id
    )
    node_ids <- record_path_node_ids(saved)
    last_ui <- saved$nodes[[node_ids[[length(node_ids)]]]]$ui
    expect_equal(last_ui[[1]]$role, "assistant")
    expect_equal(last_ui[[1]]$segments[[1]]$content, "hello (displayed)")
  })
})

test_that("editing a settled message forks at the correct transcript node", {
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
    client$set_turns(
      list(
        make_live_turn("user", "one"),
        make_live_turn("assistant", "R1")
      )
    )
    get_chat_transcript(session, "chat")$replace(
      list(
        make_ui_message("user", "one"),
        make_ui_message("assistant", "R1")
      )
    )

    ctrl <- get_session_chat_bookmark_info(session, "chat.history-controller")
    ctrl$partition <- conversation_partition(session$ns("chat"), "testuser")
    ctrl$on_response(get_turns_recorded(client))
    expect_equal(length(ctrl$record$nodes), 2)

    client$set_turns(
      list(
        make_live_turn("user", "one"),
        make_live_turn("assistant", "R1"),
        make_live_turn("user", "two"),
        make_live_turn("assistant", "R2")
      )
    )
    get_chat_transcript(session, "chat")$replace(
      list(
        make_ui_message("user", "one"),
        make_ui_message("assistant", "R1"),
        make_ui_message("user", "two"),
        make_ui_message("assistant", "R2")
      )
    )
    ctrl$on_response(get_turns_recorded(client))
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
    get_chat_transcript(session, "chat")$replace(
      list(
        make_ui_message("user", "hi"),
        make_ui_message("assistant", "hello")
      )
    )

    ctrl <- get_session_chat_bookmark_info(session, "chat.history-controller")
    ctrl$on_response(get_turns_recorded(client))
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

    new_client$set_turns(
      c(
        restored_turns,
        list(
          make_live_turn("user", "again"),
          make_live_turn("assistant", "welcome back")
        )
      )
    )
    get_chat_transcript(session, "chat")$replace(
      list(
        make_ui_message("user", "hi"),
        make_ui_message("assistant", "hello"),
        make_ui_message("user", "again"),
        make_ui_message("assistant", "welcome back")
      )
    )
    ctrl <- get_session_chat_bookmark_info(session, "chat.history-controller")
    ctrl$on_response(get_turns_recorded(new_client))
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
