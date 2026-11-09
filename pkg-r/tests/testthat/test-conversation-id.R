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
  store <- InMemoryConversationStore$new()
  ctrl <- cid_new_controller(store = store)

  id <- ctrl$ensure_conversation_id()
  expect_match(id, "^c_")
  expect_identical(ctrl$ensure_conversation_id(), id)
  expect_identical(shiny::isolate(ctrl$conversation_id()), id)

  # An identified draft has no record and leaks nothing into the store,
  # even when no save ever happens (model call failed or was cancelled).
  expect_null(ctrl$record)
  expect_length(ctrl$get_record(ctrl$partition, id) %||% list(), 0)
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

test_that("new_chat() announces the cleared ID even from an empty draft", {
  ctrl <- cid_new_controller()
  announced <- list()
  ctrl$on_active_id_change <- function(id) {
    announced[[length(announced) + 1L]] <<- list(id)
  }

  ctrl$new_chat()

  # URL restore mode relies on this to clear a stale conversation param in
  # the address bar even when the active ID was already NULL (e.g. after a
  # failed restore).
  expect_length(announced, 1L)
  expect_null(announced[[1L]][[1L]])
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
  binding_seen_by_client <- NULL
  client$stream_async <- function(...) {
    # The managed model call must already observe a non-NULL ID, both via
    # the public reactive and via its own `conversation_id` binding.
    id_seen_by_client <<- shiny::isolate(mod$history$conversation_id())
    binding_seen_by_client <<- client$conversation_id
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
      expect_null(client$conversation_id)

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
      expect_identical(binding_seen_by_client, id_seen_by_client)
      expect_identical(client$conversation_id, id_seen_by_client)
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
      ctrl_before$on_response(cid_make_turns("hi", "response"))

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
      expect_null(client$conversation_id)
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

      # Negative assertion at the store level: the swap itself writes
      # nothing, and the saved record is untouched. Guards against
      # set_client() "simplifications" that always seed the active ID.
      expect_identical(store$get(new_ctrl$partition, saved_id), saved_record)
      expect_length(store$list(new_ctrl$partition), 1)

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

# --- Client telemetry handoff -------------------------------------------------

test_that("a managed response still works for clients without the binding", {
  skip_if_not_installed("ellmer")

  client <- .make_test_client()
  client$last_turn <- function() NULL
  stream_called <- FALSE
  client$stream_async <- function(...) {
    stream_called <<- TRUE
    "response"
  }

  shiny::testServer(
    function(input, output, session) {
      chat_server(
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

      # The response runs and no member is added: identity features keep
      # working, only the telemetry handoff is skipped.
      expect_true(stream_called)
      expect_false("conversation_id" %in% names(client))
    }
  )
})

# --- Active conversation title ---------------------------------------------

# A store whose writes can be made to fail, to exercise failure ordering.
CidFlakyStore <- R6::R6Class(
  "CidFlakyStore",
  inherit = InMemoryConversationStore,
  public = list(
    fail_puts = FALSE,
    put = function(partition, record) {
      if (self$fail_puts) {
        stop("store unavailable")
      }
      super$put(partition, record)
    }
  )
)

cid_title <- function(ctrl) shiny::isolate(ctrl$title())

# Records every value an observer sees, so tests can assert on invalidation
# and not just direct reads.
cid_watch_title <- function(read, session) {
  env <- new.env(parent = emptyenv())
  env$seen <- list()
  obs <- shiny::observe({
    env$seen[[length(env$seen) + 1L]] <- list(read())
  })
  session$flushReact()
  env$obs <- obs
  env
}

cid_titles_seen <- function(env) {
  vapply(env$seen, function(x) x[[1L]] %||% NA_character_, character(1))
}

test_that("title() is NULL for an empty chat and an identified draft", {
  ctrl <- cid_new_controller()
  expect_null(cid_title(ctrl))

  ctrl$ensure_conversation_id()
  expect_false(is.null(shiny::isolate(ctrl$conversation_id())))
  expect_null(cid_title(ctrl))
})

test_that("the fallback title appears after the first successful save", {
  ctrl <- cid_new_controller()
  ctrl$ensure_conversation_id()
  ctrl$on_response(cid_make_turns("Tell me about penguins", "Sure"))

  expect_identical(cid_title(ctrl), "Tell me about penguins")
  expect_identical(cid_title(ctrl), ctrl$record$title)
})

test_that("a failed first save keeps title() NULL until a save succeeds", {
  store <- CidFlakyStore$new()
  ctrl <- cid_new_controller(store = store)
  ctrl$ensure_conversation_id()

  store$fail_puts <- TRUE
  expect_error(ctrl$on_response(cid_make_turns("Hi", "Hello")), "unavailable")
  # The record is activated in memory but was never persisted.
  expect_null(cid_title(ctrl))

  store$fail_puts <- FALSE
  turns <- c(cid_make_turns("Hi", "Hello"), cid_make_turns("More", "Sure"))
  ctrl$on_response(turns)
  expect_identical(cid_title(ctrl), "Hi")
})

test_that("a failed first save is recovered by save()", {
  store <- CidFlakyStore$new()
  ctrl <- cid_new_controller(store = store)

  store$fail_puts <- TRUE
  expect_error(ctrl$on_response(cid_make_turns("Hi", "Hello")), "unavailable")
  expect_null(cid_title(ctrl))

  store$fail_puts <- FALSE
  expect_true(ctrl$save())
  expect_identical(cid_title(ctrl), "Hi")
})

test_that("title() invalidates observers on each title change", {
  session <- shiny::MockShinySession$new()
  ctrl <- cid_new_controller(session = session)
  w <- cid_watch_title(ctrl$title, session)

  ctrl$on_response(cid_make_turns("Hi", "Hello"))
  session$flushReact()
  ctrl$rename(ctrl$record$id, "Renamed")
  session$flushReact()
  ctrl$new_chat()
  session$flushReact()

  expect_identical(cid_titles_seen(w), c(NA, "Hi", "Renamed", NA))
  w$obs$destroy()
})

test_that("rewriting an unchanged title does not invalidate observers", {
  session <- shiny::MockShinySession$new()
  ctrl <- cid_new_controller(session = session)
  ctrl$on_response(cid_make_turns("Hi", "Hello"))
  w <- cid_watch_title(ctrl$title, session)

  ctrl$rename(ctrl$record$id, "Hi")
  ctrl$save()
  session$flushReact()

  expect_identical(cid_titles_seen(w), "Hi")
  w$obs$destroy()
})

test_that("active rename updates title(); inactive rename does not", {
  ctrl <- cid_new_controller()
  id1 <- ctrl$ensure_conversation_id()
  ctrl$on_response(cid_make_turns("One", "Reply"))
  ctrl$new_chat()
  ctrl$on_response(cid_make_turns("Two", "Reply"))

  ctrl$rename(id1, "Inactive rename")
  expect_identical(cid_title(ctrl), "Two")

  ctrl$rename(ctrl$record$id, "  Active   rename ")
  expect_identical(cid_title(ctrl), "Active rename")
})

test_that("a failed rename leaves the previous title() in place", {
  store <- CidFlakyStore$new()
  ctrl <- cid_new_controller(store = store)
  ctrl$on_response(cid_make_turns("Hi", "Hello"))

  store$fail_puts <- TRUE
  expect_error(ctrl$rename(ctrl$record$id, "Nope"), "unavailable")
  expect_identical(cid_title(ctrl), "Hi")
})

test_that("restore and switch adopt the target title; new chat and delete clear it", {
  ctrl <- cid_new_controller()
  id1 <- ctrl$ensure_conversation_id()
  ctrl$on_response(cid_make_turns("One", "Reply"))
  ctrl$new_chat()
  expect_null(cid_title(ctrl))

  id2 <- ctrl$ensure_conversation_id()
  ctrl$on_response(cid_make_turns("Two", "Reply"))
  expect_identical(cid_title(ctrl), "Two")

  ctrl$switch_to(id1)
  expect_identical(cid_title(ctrl), "One")
  ctrl$switch_to(id2)
  expect_identical(cid_title(ctrl), "Two")

  ctrl$delete(id1) # inactive: unchanged
  expect_identical(cid_title(ctrl), "Two")
  ctrl$delete(id2)
  expect_null(cid_title(ctrl))
})

test_that("activating a saved record publishes its persisted title", {
  store <- InMemoryConversationStore$new()
  first <- cid_new_controller(store = store)
  first$on_response(cid_make_turns("Hi", "Hello"))
  first$rename(first$record$id, "Persisted")

  second <- cid_new_controller(store = store)
  second$activate_saved_record(store$get(second$partition, first$record$id))
  expect_identical(cid_title(second), "Persisted")
})

test_that("title = NULL still exposes the fallback and never retitles", {
  ctrl <- cid_new_controller() # history_options(title = NULL)
  ctrl$on_response(cid_make_turns("Hi", "Hello"))
  ctrl$on_response(c(
    cid_make_turns("Hi", "Hello"),
    cid_make_turns("More", "Sure")
  ))
  later::run_now(0.05)
  expect_identical(cid_title(ctrl), "Hi")
})

cid_title_controller <- function(store, title_promise) {
  local_mocked_bindings(
    generate_title = function(...) title_promise,
    .env = parent.frame()
  )
  ctrl <- HistoryController$new(
    chat_id = "chat",
    client = mock_chat_client(),
    options = history_options(store = store, title = function(turns) "x"),
    session = shiny::MockShinySession$new()
  )
  ctrl$partition <- conversation_partition("chat", "test-user")
  ctrl
}

test_that("automatic retitle updates title() once it is persisted", {
  session <- shiny::MockShinySession$new()
  ctrl <- cid_title_controller(
    InMemoryConversationStore$new(),
    promises::promise_resolve("Generated")
  )
  ctrl$on_response(cid_make_turns("Hi", "Hello"))
  expect_identical(cid_title(ctrl), "Hi")

  ctrl$on_response(c(
    cid_make_turns("Hi", "Hello"),
    cid_make_turns("More", "Sure")
  ))
  wait_until(
    function() identical(cid_title(ctrl), "Generated"),
    description = "retitle to publish"
  )
  expect_identical(ctrl$record$title, "Generated")
})

test_that("a user rename wins over an in-flight retitle", {
  resolve_title <- NULL
  pending <- promises::promise(function(resolve, reject) {
    resolve_title <<- resolve
  })
  ctrl <- cid_title_controller(InMemoryConversationStore$new(), pending)
  ctrl$on_response(cid_make_turns("Hi", "Hello"))
  ctrl$on_response(c(
    cid_make_turns("Hi", "Hello"),
    cid_make_turns("More", "Sure")
  ))

  ctrl$rename(ctrl$record$id, "Mine")
  resolve_title("Generated")
  done <- FALSE
  promises::then(pending, function(...) done <<- TRUE)
  wait_until(function() done, description = "retitle callback")

  expect_identical(cid_title(ctrl), "Mine")
  expect_identical(ctrl$record$title, "Mine")
})

test_that("a failed retitle persistence leaves title() unchanged", {
  store <- CidFlakyStore$new()
  resolve_title <- NULL
  pending <- promises::promise(function(resolve, reject) {
    resolve_title <<- resolve
  })
  ctrl <- cid_title_controller(store, pending)
  ctrl$on_response(cid_make_turns("Hi", "Hello"))
  ctrl$on_response(c(
    cid_make_turns("Hi", "Hello"),
    cid_make_turns("More", "Sure")
  ))

  store$fail_puts <- TRUE
  resolve_title("Generated")
  settled <- FALSE
  promises::then(pending, function(...) settled <<- TRUE)
  wait_until(function() settled, description = "retitle callback")
  later::run_now(0.1)

  expect_identical(cid_title(ctrl), "Hi")
})

test_that("chat$history$title() follows the submission and response lifecycle", {
  skip_if_not_installed("ellmer")

  client <- mock_chat_client()
  mod <- NULL
  title_during_call <- "unset"
  client$stream_async <- function(...) {
    # Mid-call the conversation is an identified, unsaved draft.
    title_during_call <<- shiny::isolate(mod$history$title())
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
      expect_null(shiny::isolate(mod$history$title()))

      session$setInputs(
        chat_history_browser_token = "tok",
        chat_user_input = "hi there"
      )
      cid_pump(session)
      expect_null(title_during_call)

      ctrl <- get_session_chat_bookmark_info(
        session,
        "chat.history-controller"
      )
      expect_false(is.null(ctrl$record))
      expect_identical(shiny::isolate(mod$history$title()), ctrl$record$title)

      ctrl$rename(ctrl$record$id, "Renamed")
      expect_identical(shiny::isolate(mod$history$title()), "Renamed")

      ctrl$new_chat()
      expect_null(shiny::isolate(mod$history$title()))
    }
  )
})

test_that("with history = FALSE chat$history$title() stays NULL", {
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
      expect_null(shiny::isolate(mod$history$title()))
    }
  )
})

test_that("set_client() preserves the active saved title", {
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
        chat_user_input = "hi there"
      )
      cid_pump(session)
      ctrl_before <- get_session_chat_bookmark_info(
        session,
        "chat.history-controller"
      )
      ctrl_before$on_response(cid_make_turns("hi there", "response"))
      ctrl_before$rename(ctrl_before$record$id, "Kept title")

      new_client <- mock_chat_client()
      new_client$stream_async <- function(...) "response"
      mod$set_client(new_client)
      cid_pump(session)

      ctrl_after <- get_session_chat_bookmark_info(
        session,
        "chat.history-controller"
      )
      expect_false(identical(ctrl_before, ctrl_after))
      expect_identical(shiny::isolate(mod$history$title()), "Kept title")
    }
  )
})
