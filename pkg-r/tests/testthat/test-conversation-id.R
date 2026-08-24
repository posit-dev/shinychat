cid_make_turns <- function(user_text = "Hi", asst_text = "Hello") {
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

cid_new_controller <- function(
  store = InMemoryConversationStore$new(),
  client = mock_chat_client(),
  session = shiny::MockShinySession$new()
) {
  ctrl <- HistoryController$new(
    chat_id = "chat",
    client = client,
    options = history_options(store = store, title = NULL),
    session = session
  )
  ctrl$partition <- conversation_partition("chat", "test-user")
  ctrl
}

# Drain pending async work and reactive flushes for a MockShinySession.
cid_pump <- function(session, n = 10) {
  for (i in seq_len(n)) {
    later::run_now(0.05)
    session$flushReact()
  }
}

# Pump until the response task settles. Async stream consumption is scheduled
# over many event-loop ticks, so a fixed handful of pumps is not enough.
cid_wait_idle <- function(session, mod, timeout = 5) {
  deadline <- Sys.time() + timeout
  while (shiny::isolate(mod$status()) != "idle" && Sys.time() < deadline) {
    later::run_now(0.05)
    session$flushReact()
  }
  cid_pump(session)
}

# --- Controller lifecycle ---------------------------------------------------

test_that("a new controller has no conversation ID", {
  ctrl <- cid_new_controller()
  expect_null(shiny::isolate(ctrl$conversation_id()))
  expect_null(ctrl$record)
})

test_that("ensure_conversation_id() allocates once and returns it stably", {
  ctrl <- cid_new_controller()

  id <- ctrl$ensure_conversation_id()
  expect_match(id, "^c_")
  expect_identical(ctrl$ensure_conversation_id(), id)
  expect_identical(shiny::isolate(ctrl$conversation_id()), id)

  # An identified draft has no record and is not in the store.
  expect_null(ctrl$record)
  expect_length(ctrl$get_record(ctrl$partition, id) %||% list(), 0)
})

test_that("an unsaved draft retains its ID (failure/cancellation before save)", {
  store <- InMemoryConversationStore$new()
  ctrl <- cid_new_controller(store = store)

  id <- ctrl$ensure_conversation_id()

  # No save happens (model call failed or was cancelled); the ID survives
  # and nothing leaks into the store.
  expect_identical(ctrl$ensure_conversation_id(), id)
  expect_identical(shiny::isolate(ctrl$conversation_id()), id)
  expect_null(ctrl$record)
  expect_length(store$list(ctrl$partition), 0)
})

test_that("the first saved record uses the preallocated ID", {
  ctrl <- cid_new_controller()

  id <- ctrl$ensure_conversation_id()
  ctrl$on_response(cid_make_turns())

  expect_false(is.null(ctrl$record))
  expect_identical(ctrl$record$id, id)
  expect_identical(shiny::isolate(ctrl$conversation_id()), id)
})

test_that("first save without a prior ensure allocates the ID at save time", {
  # Standalone chat_enable_history() users never call
  # ensure_conversation_id(); the save path must still converge on a single
  # ID shared by the record and the active identity.
  ctrl <- cid_new_controller()

  ctrl$on_response(cid_make_turns())

  expect_false(is.null(ctrl$record))
  expect_identical(shiny::isolate(ctrl$conversation_id()), ctrl$record$id)
})

test_that("later saves keep the same ID", {
  ctrl <- cid_new_controller()

  id <- ctrl$ensure_conversation_id()
  ctrl$on_response(cid_make_turns("Hi", "Hello"))
  ctrl$on_response(c(
    cid_make_turns("Hi", "Hello"),
    cid_make_turns("Again", "Reply")
  ))

  expect_identical(ctrl$record$id, id)
  expect_identical(shiny::isolate(ctrl$conversation_id()), id)
})

test_that("switch_to() adopts the stored record ID", {
  ctrl <- cid_new_controller()

  id1 <- ctrl$ensure_conversation_id()
  ctrl$on_response(cid_make_turns("One", "Reply one"))

  ctrl$new_chat()
  expect_null(shiny::isolate(ctrl$conversation_id()))

  id2 <- ctrl$ensure_conversation_id()
  expect_false(identical(id2, id1))
  ctrl$on_response(cid_make_turns("Two", "Reply two"))

  ctrl$switch_to(id1)
  expect_identical(shiny::isolate(ctrl$conversation_id()), id1)
  expect_identical(ctrl$record$id, id1)

  ctrl$switch_to(id2)
  expect_identical(shiny::isolate(ctrl$conversation_id()), id2)
  expect_identical(ctrl$record$id, id2)
})

test_that("a failed switch leaves the current ID unchanged", {
  ctrl <- cid_new_controller()

  id <- ctrl$ensure_conversation_id()
  ctrl$on_response(cid_make_turns())

  expect_error(ctrl$switch_to("c_nonexistent"), "Conversation not found")
  expect_identical(shiny::isolate(ctrl$conversation_id()), id)
  expect_identical(ctrl$record$id, id)
})

test_that("edit and sibling navigation retain the conversation ID", {
  session <- shiny::MockShinySession$new()
  ctrl <- cid_new_controller(session = session)

  report_messages <- function(texts) {
    roles <- rep(c("user", "assistant"), length.out = length(texts))
    messages <- Map(
      function(role, text) {
        list(
          role = role,
          segments = list(list(content = text, content_type = "markdown"))
        )
      },
      roles,
      texts
    )
    session$setInputs(chat_messages = messages)
  }

  id <- ctrl$ensure_conversation_id()

  report_messages(c("Hi", "Hello"))
  ctrl$on_response(cid_make_turns("Hi", "Hello"))
  expect_identical(shiny::isolate(ctrl$conversation_id()), id)

  # Fork the conversation by editing the first message, then navigate
  # between the sibling branches: the ID must not move.
  ctrl$handle_edit(0, "Hi again", NULL)
  expect_identical(shiny::isolate(ctrl$conversation_id()), id)

  report_messages(c("Hi again", "New reply"))
  ctrl$on_response(cid_make_turns("Hi again", "New reply"))
  expect_identical(shiny::isolate(ctrl$conversation_id()), id)

  ctrl$handle_navigate(0, "prev")
  expect_identical(shiny::isolate(ctrl$conversation_id()), id)
  expect_identical(ctrl$record$id, id)
})

test_that("new_chat() clears the ID and the next submission reallocates", {
  ctrl <- cid_new_controller()

  id1 <- ctrl$ensure_conversation_id()
  ctrl$on_response(cid_make_turns())

  ctrl$new_chat()
  expect_null(ctrl$record)
  expect_null(shiny::isolate(ctrl$conversation_id()))

  id2 <- ctrl$ensure_conversation_id()
  expect_false(identical(id2, id1))
})

test_that("deleting the active conversation clears the ID", {
  ctrl <- cid_new_controller()

  id <- ctrl$ensure_conversation_id()
  ctrl$on_response(cid_make_turns())

  ctrl$delete(id)
  expect_null(ctrl$record)
  expect_null(shiny::isolate(ctrl$conversation_id()))
})

test_that("a replacement controller inherits an unsaved draft ID", {
  store <- InMemoryConversationStore$new()
  old <- cid_new_controller(store = store)
  id <- old$ensure_conversation_id()

  new <- cid_new_controller(store = store)
  new$seed_conversation_id(id)

  # Seeded, not saved: no record exists yet, but the ID is carried over and
  # is never reallocated.
  expect_null(new$record)
  expect_identical(shiny::isolate(new$conversation_id()), id)
  expect_identical(new$ensure_conversation_id(), id)

  new$on_response(cid_make_turns())
  expect_identical(new$record$id, id)
})

test_that("a replacement controller inherits a saved conversation ID", {
  store <- InMemoryConversationStore$new()
  old <- cid_new_controller(store = store)
  id <- old$ensure_conversation_id()
  old$on_response(cid_make_turns())

  new <- cid_new_controller(store = store)
  new$seed_conversation_id(id)
  expect_identical(shiny::isolate(new$conversation_id()), id)

  # Normal initialization restores the record and confirms the same ID.
  target <- new$get_record(new$partition, id)
  new$activate_record(target)
  expect_identical(new$record$id, id)
  expect_identical(shiny::isolate(new$conversation_id()), id)
})

test_that("seed_conversation_id() refuses to seed over an active record", {
  ctrl <- cid_new_controller()
  ctrl$on_response(cid_make_turns())
  expect_error(
    ctrl$seed_conversation_id("c_other"),
    "active record"
  )
})

test_that("on_active_id_change fires on allocation and clearing, not on save", {
  ctrl <- cid_new_controller()

  calls <- list()
  ctrl$on_active_id_change <- function(id) {
    calls[[length(calls) + 1]] <<- list(id)
  }

  id <- ctrl$ensure_conversation_id()
  ctrl$ensure_conversation_id() # stable: no refire
  ctrl$on_response(cid_make_turns()) # same ID: no refire
  ctrl$new_chat() # cleared: fires NULL

  expect_equal(calls, list(list(id), list(NULL)))
})

# --- chat_server() integration ----------------------------------------------

test_that("conversation_id() is NULL initially and allocated before the first model call", {
  skip_if_not_installed("ellmer")

  client <- mock_chat_client()
  mod <- NULL
  id_seen_by_client <- NULL
  client$stream_async <- function(...) {
    # The managed model call must already observe a non-NULL ID.
    id_seen_by_client <<- shiny::isolate(mod$history$conversation_id())
    "response"
  }

  shiny::testServer(
    function(input, output, session) {
      mod <<- chat_server(
        "chat",
        client,
        history = history_options(store = "memory", title = NULL),
        session = session
      )
    },
    {
      expect_null(shiny::isolate(mod$history$conversation_id()))

      session$setInputs(
        chat_history_browser_token = "tok",
        chat_user_input = "hi"
      )
      cid_pump(session)

      expect_false(is.null(id_seen_by_client))
      expect_identical(
        shiny::isolate(mod$history$conversation_id()),
        id_seen_by_client
      )
    }
  )
})

test_that("the public reactive and the stored record report the same ID", {
  skip_if_not_installed("ellmer")

  client <- mock_chat_client()
  mod <- NULL
  client$stream_async <- function(...) "response"

  shiny::testServer(
    function(input, output, session) {
      mod <<- chat_server(
        "chat",
        client,
        history = history_options(store = "memory", title = NULL),
        session = session
      )
    },
    {
      session$setInputs(
        chat_history_browser_token = "tok",
        chat_user_input = "hi"
      )
      cid_pump(session)

      ctrl <- get_session_chat_bookmark_info(
        session,
        "chat.history-controller"
      )
      ctrl$on_response(cid_make_turns())

      expect_identical(
        ctrl$record$id,
        shiny::isolate(mod$history$conversation_id())
      )
    }
  )
})

test_that("failed and retried calls report the same conversation ID", {
  skip_if_not_installed("ellmer")

  session <- shiny::MockShinySession$new()
  client <- mock_chat_client()
  mod <- NULL
  attempts <- 0
  ids_seen <- character(0)
  client$stream_async <- function(...) {
    attempts <<- attempts + 1
    ids_seen <<- c(ids_seen, shiny::isolate(mod$history$conversation_id()))
    if (attempts == 1) {
      stop("boom")
    }
    "recovered"
  }

  # Driven against a session we keep open, since settling an ExtendedTask and
  # then letting testServer() tear its session down leaks an unhandled
  # rejection.
  mod <- shiny::withReactiveDomain(session, {
    chat_server(
      "chat",
      client,
      history = history_options(store = "memory", title = NULL),
      session = session
    )
  })

  shiny::withReactiveDomain(session, {
    session$setInputs(chat_history_browser_token = "tok")
    session$flushReact()

    suppressWarnings(session$setInputs(chat_user_input = "hi"))
    deadline <- Sys.time() + 5
    while (is.null(shiny::isolate(mod$last_error())) && Sys.time() < deadline) {
      later::run_now(0.05)
      session$flushReact()
    }
    expect_false(is.null(shiny::isolate(mod$last_error())))

    session$setInputs(chat_user_input = "retry")
    deadline <- Sys.time() + 5
    while (
      (!is.null(shiny::isolate(mod$last_error())) ||
        shiny::isolate(mod$status()) != "idle") &&
        Sys.time() < deadline
    ) {
      later::run_now(0.05)
      session$flushReact()
    }
    later::run_now(0.05)
    session$flushReact()

    expect_equal(attempts, 2)
    expect_length(ids_seen, 2)
    expect_identical(ids_seen[[1]], ids_seen[[2]])
  })
})

test_that("restore and switch update the public conversation_id() reactive", {
  skip_if_not_installed("ellmer")

  client <- mock_chat_client()
  mod <- NULL
  client$stream_async <- function(...) "response"

  shiny::testServer(
    function(input, output, session) {
      mod <<- chat_server(
        "chat",
        client,
        history = history_options(store = "memory", title = NULL),
        session = session
      )
    },
    {
      session$setInputs(
        chat_history_browser_token = "tok",
        chat_user_input = "one"
      )
      cid_pump(session)

      ctrl <- get_session_chat_bookmark_info(
        session,
        "chat.history-controller"
      )
      ctrl$on_response(cid_make_turns("one", "reply one"))
      id1 <- shiny::isolate(mod$history$conversation_id())

      ctrl$new_chat()
      expect_null(shiny::isolate(mod$history$conversation_id()))

      session$setInputs(chat_user_input = "two")
      cid_pump(session)
      ctrl$on_response(cid_make_turns("two", "reply two"))
      id2 <- shiny::isolate(mod$history$conversation_id())
      expect_false(identical(id1, id2))

      ctrl$switch_to(id1)
      expect_identical(shiny::isolate(mod$history$conversation_id()), id1)
    }
  )
})

test_that("set_client() preserves the conversation ID", {
  skip_if_not_installed("ellmer")

  client <- mock_chat_client()
  mod <- NULL
  client$stream_async <- function(...) "response"

  shiny::testServer(
    function(input, output, session) {
      mod <<- chat_server(
        "chat",
        client,
        history = history_options(store = "memory", title = NULL),
        session = session
      )
    },
    {
      session$setInputs(
        chat_history_browser_token = "tok",
        chat_user_input = "hi"
      )
      cid_pump(session)
      id <- shiny::isolate(mod$history$conversation_id())
      expect_false(is.null(id))

      ctrl_before <- get_session_chat_bookmark_info(
        session,
        "chat.history-controller"
      )

      new_client <- mock_chat_client()
      new_client$stream_async <- function(...) "response"
      mod$set_client(new_client)
      cid_pump(session)

      ctrl_after <- get_session_chat_bookmark_info(
        session,
        "chat.history-controller"
      )
      expect_false(identical(ctrl_before, ctrl_after))
      expect_identical(shiny::isolate(mod$history$conversation_id()), id)

      # The replacement controller never reallocates the inherited ID.
      expect_identical(ctrl_after$ensure_conversation_id(), id)
    }
  )
})

test_that("with history = FALSE the conversation_id() reactive stays NULL", {
  skip_if_not_installed("ellmer")

  client <- mock_chat_client()
  mod <- NULL
  client$stream_async <- function(...) "response"

  shiny::testServer(
    function(input, output, session) {
      mod <<- chat_server("chat", client, history = FALSE, session = session)
    },
    {
      session$setInputs(chat_user_input = "hi")
      cid_pump(session)
      expect_null(shiny::isolate(mod$history$conversation_id()))
    }
  )
})

test_that("set_client() does not seed a saved conversation's ID", {
  skip_if_not_installed("ellmer")

  store <- InMemoryConversationStore$new()
  client <- mock_chat_client()
  mod <- NULL
  client$stream_async <- function(...) "response"

  shiny::testServer(
    function(input, output, session) {
      mod <<- chat_server(
        "chat",
        client,
        # init never restores in this mode, so a seeded saved-ID would be
        # orphaned and the next save would overwrite the stored record.
        history = history_options(
          store = store,
          title = NULL,
          restore_mode = "none"
        ),
        session = session
      )
    },
    {
      session$setInputs(
        chat_history_browser_token = "tok",
        chat_user_input = "hi"
      )
      cid_wait_idle(session, mod)

      # Save the active conversation: its ID now belongs to a stored record.
      ctrl <- get_session_chat_bookmark_info(
        session,
        "chat.history-controller"
      )
      ctrl$on_response(cid_make_turns())
      saved_id <- ctrl$record$id
      saved_record <- ctrl$record
      expect_false(is.null(saved_id))

      new_client <- mock_chat_client()
      new_client$stream_async <- function(...) "fresh response"
      mod$set_client(new_client, sync = FALSE)
      cid_pump(session)

      # The replacement controller must not inherit the saved ID.
      new_ctrl <- get_session_chat_bookmark_info(
        session,
        "chat.history-controller"
      )
      expect_null(new_ctrl$record)
      expect_null(shiny::isolate(new_ctrl$conversation_id()))

      # The next submission mints a fresh ID, and the stored conversation
      # survives the swap untouched.
      session$setInputs(chat_user_input = "hello again")
      cid_wait_idle(session, mod)
      new_ctrl$on_response(cid_make_turns(user_text = "hello again"))

      expect_false(identical(new_ctrl$record$id, saved_id))
      expect_identical(store$get(new_ctrl$partition, saved_id), saved_record)
    }
  )
})

# Regression: the greeting block in chat_server() used to assign a plain
# local over the `history_controller` reactiveVal, breaking every
# submission (and conversation_id()) whenever `greeting` was set.
test_that("submission and conversation_id() work when greeting is set", {
  skip_if_not_installed("ellmer")

  client <- mock_chat_client()
  mod <- NULL
  client$stream_async <- function(...) "response"

  shiny::testServer(
    function(input, output, session) {
      mod <<- chat_server(
        "chat",
        client,
        greeting = "Hello!",
        history = history_options(store = "memory", title = NULL),
        session = session
      )
    },
    {
      session$setInputs(
        chat_history_browser_token = "tok",
        chat_user_input = "hi"
      )
      cid_wait_idle(session, mod)

      expect_identical(shiny::isolate(mod$status()), "idle")
      expect_match(shiny::isolate(mod$history$conversation_id()), "^c_")
    }
  )
})

# --- OpenTelemetry ------------------------------------------------------------

test_that("a managed response produces one shinychat.response span carrying the ID", {
  skip_if_not_installed("ellmer")
  skip_if_not_installed("otelsdk")

  session <- shiny::MockShinySession$new()
  client <- mock_chat_client()
  mod <- NULL
  client$stream_async <- function(...) {
    # A child span, as Commons/ellmer would emit inside the model call.
    span <- otel::get_tracer("test")$start_span("inner_model_call")
    span$end()
    "response"
  }

  recorded <- otelsdk::with_otel_record({
    mod <- shiny::withReactiveDomain(session, {
      chat_server(
        "chat",
        client,
        history = history_options(store = "memory", title = NULL),
        session = session
      )
    })
    shiny::withReactiveDomain(session, {
      session$setInputs(chat_history_browser_token = "tok")
      session$flushReact()
      session$setInputs(chat_user_input = "hi")
      cid_wait_idle(session, mod)
    })
  })

  spans <- recorded$traces
  response_spans <- spans[names(spans) == "shinychat.response"]
  expect_length(response_spans, 1)

  span <- response_spans[[1]]
  expect_equal(span$kind, "internal")
  expect_identical(
    span$attributes[["gen_ai.conversation.id"]],
    shiny::isolate(mod$history$conversation_id())
  )

  # The inner model span is a descendant of the response span.
  inner <- spans[["inner_model_call"]]
  expect_false(is.null(inner))
  expect_identical(inner$parent, span$span_id)
})

test_that("the response span stays active through lazy stream consumption", {
  skip_if_not_installed("ellmer")
  skip_if_not_installed("otelsdk")

  session <- shiny::MockShinySession$new()
  client <- mock_chat_client()
  mod <- NULL
  active_span_id_during_stream <- NULL
  client$stream_async <- function(...) {
    coro::async_generator(function() {
      # Runs when chat_append() consumes the stream, after stream_async()
      # has returned: the response span must still be active here.
      active <- otel::get_active_span()
      if (!is.null(active)) {
        active_span_id_during_stream <<- active$get_context()$get_span_id()
      }
      yield("chunk")
    })()
  }

  recorded <- otelsdk::with_otel_record({
    mod <- shiny::withReactiveDomain(session, {
      chat_server(
        "chat",
        client,
        history = history_options(store = "memory", title = NULL),
        session = session
      )
    })
    shiny::withReactiveDomain(session, {
      session$setInputs(chat_history_browser_token = "tok")
      session$flushReact()
      session$setInputs(chat_user_input = "hi")
      cid_wait_idle(session, mod)
    })
  })

  span <- recorded$traces[["shinychat.response"]]
  expect_false(is.null(span))
  expect_false(is.null(active_span_id_during_stream))
  expect_identical(active_span_id_during_stream, span$span_id)
})

test_that("failure closes the span without changing the conversation ID", {
  skip_if_not_installed("ellmer")
  skip_if_not_installed("otelsdk")

  session <- shiny::MockShinySession$new()
  client <- mock_chat_client()
  mod <- NULL
  attempts <- 0
  client$stream_async <- function(...) {
    attempts <<- attempts + 1
    if (attempts == 1) {
      stop("boom")
    }
    "recovered"
  }

  recorded <- otelsdk::with_otel_record({
    mod <- shiny::withReactiveDomain(session, {
      chat_server(
        "chat",
        client,
        history = history_options(store = "memory", title = NULL),
        session = session
      )
    })
    shiny::withReactiveDomain(session, {
      session$setInputs(chat_history_browser_token = "tok")
      session$flushReact()

      suppressWarnings(session$setInputs(chat_user_input = "hi"))
      deadline <- Sys.time() + 5
      while (
        is.null(shiny::isolate(mod$last_error())) && Sys.time() < deadline
      ) {
        later::run_now(0.05)
        session$flushReact()
      }

      session$setInputs(chat_user_input = "retry")
      deadline <- Sys.time() + 5
      while (
        (!is.null(shiny::isolate(mod$last_error())) ||
          shiny::isolate(mod$status()) != "idle") &&
          Sys.time() < deadline
      ) {
        later::run_now(0.05)
        session$flushReact()
      }
      later::run_now(0.05)
      session$flushReact()
    })
  })

  id <- shiny::isolate(mod$history$conversation_id())
  expect_equal(attempts, 2)

  spans <- recorded$traces
  response_spans <- spans[names(spans) == "shinychat.response"]
  # Both the failed and the retried response produced a span, each closed
  # with the same captured conversation ID.
  expect_length(response_spans, 2)
  for (span in response_spans) {
    expect_identical(span$attributes[["gen_ai.conversation.id"]], id)
  }
})

test_that("history-disabled responses produce no shinychat.response span", {
  skip_if_not_installed("ellmer")
  skip_if_not_installed("otelsdk")

  session <- shiny::MockShinySession$new()
  client <- mock_chat_client()
  mod <- NULL
  client$stream_async <- function(...) "response"

  recorded <- otelsdk::with_otel_record({
    mod <- shiny::withReactiveDomain(session, {
      chat_server("chat", client, history = FALSE, session = session)
    })
    shiny::withReactiveDomain(session, {
      session$setInputs(chat_user_input = "hi")
      cid_wait_idle(session, mod)
    })
  })

  expect_false("shinychat.response" %in% names(recorded$traces))
  expect_null(shiny::isolate(mod$history$conversation_id()))
})
