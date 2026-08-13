library(htmltools)

# Helper: create a mock session and collect custom messages sent to it.
# Uses an environment so the message list is captured by reference.
mock_session_with_spy <- function() {
  sess <- shiny::MockShinySession$new()
  spy_env <- new.env(parent = emptyenv())
  spy_env$messages <- list()
  sess$sendCustomMessage <- function(type, msg) {
    spy_env$messages[[length(spy_env$messages) + 1]] <- list(
      type = type,
      message = msg
    )
  }
  list(session = sess, spy_env = spy_env)
}

# Return the custom messages recorded by a spy session.
spy_messages <- function(spy) spy$spy_env$messages

# ── chat_greeting() ────────────────────────────────────────────────────────────

test_that("chat_greeting() returns class 'chat_greeting' with all fields", {
  g <- chat_greeting("Hello")
  expect_s3_class(g, "chat_greeting")
  expect_equal(g$content, "Hello")
  expect_false(g$persistent)
})

test_that("chat_greeting() stores non-default option values", {
  g <- chat_greeting("Hi", persistent = TRUE)
  expect_true(g$persistent)
})

test_that("chat_greeting() accepts HTML() content", {
  g <- chat_greeting(HTML("<b>bold</b>"))
  expect_s3_class(g, "chat_greeting")
  expect_s3_class(g$content, "html")
  expect_equal(as.character(g$content), "<b>bold</b>")
})

test_that("chat_greeting() accepts htmltools tag content", {
  tag_content <- tags$div("Welcome")
  g <- chat_greeting(tag_content)
  expect_s3_class(g, "chat_greeting")
  expect_s3_class(g$content, "shiny.tag")
})

# ── chat_ui(greeting = ...) ───────────────────────────────────────────────────

test_that("chat_ui() plain string greeting produces markdown content_type and persistent=FALSE", {
  ui <- chat_ui("chat", greeting = "## Hello")
  attr_raw <- ui$attribs$greeting
  expect_false(is.null(attr_raw))
  payload <- jsonlite::fromJSON(attr_raw)
  expect_equal(payload$content, "## Hello")
  expect_equal(payload$content_type, "markdown")
  expect_false(payload$options$persistent)
})

test_that("chat_ui() chat_greeting with persistent=TRUE serializes correctly", {
  g <- chat_greeting("## Hi", persistent = TRUE)
  ui <- chat_ui("chat", greeting = g)
  payload <- jsonlite::fromJSON(ui$attribs$greeting)
  expect_equal(payload$content, "## Hi")
  expect_equal(payload$content_type, "markdown")
  expect_true(payload$options$persistent)
})

test_that("chat_ui() HTML() greeting produces html content_type", {
  ui <- chat_ui("chat", greeting = HTML("<b>hi</b>"))
  payload <- jsonlite::fromJSON(ui$attribs$greeting)
  expect_equal(payload$content_type, "html")
  expect_equal(payload$content, "<b>hi</b>")
})

test_that("chat_ui() tag greeting produces html content_type and attaches dependencies", {
  tag_content <- tags$div("Hello", class = "greeting")
  ui <- chat_ui("chat", greeting = tag_content)
  payload <- jsonlite::fromJSON(ui$attribs$greeting)
  expect_equal(payload$content_type, "html")
  deps <- htmltools::findDependencies(ui)
  dep_names <- vapply(deps, `[[`, character(1), "name")
  expect_true("shinychat" %in% dep_names)
})

test_that("chat_ui() tag with explicit htmlDependency attaches that dep", {
  tag_content <- tags$div(
    "Hello",
    htmlDependency("my-dep", "1.0.0", ".")
  )
  ui <- chat_ui("chat", greeting = tag_content)
  deps <- htmltools::findDependencies(ui)
  dep_names <- vapply(deps, `[[`, character(1), "name")
  expect_true("my-dep" %in% dep_names)
})

test_that("chat_ui() rejects generator as greeting", {
  gen <- coro::async_generator(function() yield("x"))
  expect_error(
    chat_ui("chat", greeting = gen()),
    regexp = "generator or promise"
  )
})

test_that("chat_ui() snapshot for plain string greeting", {
  expect_snapshot(chat_ui("chat", greeting = "## Welcome!"))
})

test_that("chat_ui() snapshot for chat_greeting with persistent=TRUE", {
  expect_snapshot(
    chat_ui(
      "chat",
      greeting = chat_greeting("## Hi", persistent = TRUE)
    )
  )
})

# ── chat_set_greeting() ───────────────────────────────────────────────────────

test_that("chat_set_greeting() NULL sends greeting_clear action", {
  spy <- mock_session_with_spy()
  shiny::withReactiveDomain(spy$session, {
    chat_set_greeting("chat", NULL, session = spy$session)
  })
  msgs <- spy_messages(spy)
  expect_length(msgs, 1)
  expect_equal(msgs[[1]]$type, "shinyChatMessage")
  expect_equal(msgs[[1]]$message$action$type, "greeting_clear")
})

test_that("chat_set_greeting() plain string sends greeting action with markdown content_type", {
  spy <- mock_session_with_spy()
  shiny::withReactiveDomain(spy$session, {
    chat_set_greeting("chat", "Hello", session = spy$session)
  })
  msgs <- spy_messages(spy)
  expect_length(msgs, 1)
  action <- msgs[[1]]$message$action
  expect_equal(action$type, "greeting")
  expect_equal(action$content_type, "markdown")
  expect_false(action$options$persistent)
})

test_that("chat_set_greeting() HTML() content sends html content_type", {
  spy <- mock_session_with_spy()
  shiny::withReactiveDomain(spy$session, {
    chat_set_greeting(
      "chat",
      chat_greeting(HTML("<b>hi</b>")),
      session = spy$session
    )
  })
  msgs <- spy_messages(spy)
  action <- msgs[[1]]$message$action
  expect_equal(action$type, "greeting")
  expect_equal(action$content_type, "html")
  expect_equal(action$content, "<b>hi</b>")
})

test_that("chat_set_greeting() generator sends greeting_start, greeting_chunk(s), greeting_end", {
  spy <- mock_session_with_spy()
  chunks <- c("He", "ll", "o")
  gen <- coro::async_generator(function() {
    for (ch in chunks) {
      yield(ch)
    }
  })
  shiny::withReactiveDomain(spy$session, {
    p <- chat_set_greeting("chat", chat_greeting(gen()), session = spy$session)
    done <- FALSE
    promises::then(
      p,
      function(x) {
        done <<- TRUE
      },
      function(e) {
        done <<- TRUE
      }
    )
    while (!done) {
      later::run_now(0.1)
    }
  })
  msgs <- spy_messages(spy)
  action_types <- vapply(msgs, function(m) m$message$action$type, character(1))
  expect_equal(action_types[[1]], "greeting_start")
  expect_equal(action_types[[length(action_types)]], "greeting_end")
  chunk_types <- action_types[action_types == "greeting_chunk"]
  expect_gte(length(chunk_types), 1)
  chunk_msgs <- Filter(
    function(m) m$message$action$type == "greeting_chunk",
    msgs
  )
  operations <- vapply(
    chunk_msgs,
    function(m) m$message$action$operation,
    character(1)
  )
  expect_true(all(operations == "append"))

  expect_identical(
    get_session_greeting_state(spy$session, "chat"),
    list(
      content = "Hello",
      content_type = "markdown",
      options = list(persistent = FALSE),
      html_deps = list()
    )
  )
})

test_that("chat_set_greeting() does not store a snapshot when the stream errors", {
  spy <- mock_session_with_spy()
  gen <- coro::async_generator(function() {
    yield("He")
    stop("boom")
  })
  shiny::withReactiveDomain(spy$session, {
    p <- chat_set_greeting("chat", chat_greeting(gen()), session = spy$session)
    done <- FALSE
    promises::then(
      p,
      function(x) {
        done <<- TRUE
      },
      function(e) {
        done <<- TRUE
      }
    )
    while (!done) {
      later::run_now(0.1)
    }
  })
  expect_null(get_session_greeting_state(spy$session, "chat"))
})

test_that("chat_set_greeting() streamed HTML/tag chunks store content_type='html' and their html_deps", {
  spy <- mock_session_with_spy()
  tag_chunk <- tags$div("Hi", htmlDependency("my-greeting-dep", "1.0.0", "."))
  gen <- coro::async_generator(function() {
    yield(tag_chunk)
  })
  shiny::withReactiveDomain(spy$session, {
    p <- chat_set_greeting("chat", chat_greeting(gen()), session = spy$session)
    done <- FALSE
    promises::then(
      p,
      function(x) {
        done <<- TRUE
      },
      function(e) {
        done <<- TRUE
      }
    )
    while (!done) {
      later::run_now(0.1)
    }
  })

  state <- get_session_greeting_state(spy$session, "chat")
  expect_equal(state$content_type, "html")
  expect_true(length(state$html_deps) > 0)
  dep_names <- vapply(state$html_deps, `[[`, character(1), "name")
  expect_true("my-greeting-dep" %in% dep_names)

  # The stored html_deps must match what was actually sent while streaming,
  # not an empty placeholder based on a hardcoded "always markdown" assumption.
  msgs <- spy_messages(spy)
  chunk_msg <- Filter(
    function(m) identical(m$message$action$type, "greeting_chunk"),
    msgs
  )[[1]]
  expect_identical(chunk_msg$message$html_deps, state$html_deps)
})

test_that("chat_set_greeting() dedupes html_deps repeated across streamed chunks", {
  spy <- mock_session_with_spy()
  gen <- coro::async_generator(function() {
    yield(tags$div("One", htmlDependency("my-greeting-dep", "1.0.0", ".")))
    yield(tags$div("Two", htmlDependency("my-greeting-dep", "1.0.0", ".")))
  })
  shiny::withReactiveDomain(spy$session, {
    p <- chat_set_greeting("chat", chat_greeting(gen()), session = spy$session)
    done <- FALSE
    promises::then(
      p,
      function(x) {
        done <<- TRUE
      },
      function(e) {
        done <<- TRUE
      }
    )
    while (!done) {
      later::run_now(0.1)
    }
  })

  state <- get_session_greeting_state(spy$session, "chat")
  dep_names <- vapply(state$html_deps, `[[`, character(1), "name")
  expect_equal(sum(dep_names == "my-greeting-dep"), 1)
})

# ── Complete greeting snapshot state (content, content_type, options, html_deps) ──

test_that("chat_set_greeting() static HTML persistent greeting stores complete four-field snapshot", {
  spy <- mock_session_with_spy()
  shiny::withReactiveDomain(spy$session, {
    chat_set_greeting(
      "chat",
      chat_greeting(HTML("<strong>Welcome</strong>"), persistent = TRUE),
      session = spy$session
    )
  })
  expect_identical(
    get_session_greeting_state(spy$session, "chat"),
    list(
      content = "<strong>Welcome</strong>",
      content_type = "html",
      options = list(persistent = TRUE),
      html_deps = list()
    )
  )
})

test_that("restore_greeting_snapshot() sends the original recipe and passes html_deps", {
  spy <- mock_session_with_spy()
  snapshot <- list(
    content = "<strong>Welcome</strong>",
    content_type = "html",
    options = list(persistent = TRUE),
    html_deps = list(list(name = "greeting-style", version = "1.0.0"))
  )
  restore_greeting_snapshot("chat", snapshot, session = spy$session)

  msgs <- spy_messages(spy)
  expect_length(msgs, 1)
  expect_identical(
    msgs[[1]]$message$action,
    list(
      type = "greeting",
      content = snapshot$content,
      content_type = snapshot$content_type,
      options = snapshot$options
    )
  )
  expect_identical(msgs[[1]]$message$html_deps, snapshot$html_deps)
  expect_identical(get_session_greeting_state(spy$session, "chat"), snapshot)
})

test_that("restore_greeting_snapshot() rejects content-only legacy state with no compatibility fallback", {
  spy <- mock_session_with_spy()
  expect_error(
    restore_greeting_snapshot(
      "chat",
      list(content = "Hello"),
      session = spy$session
    ),
    "invalid or missing"
  )
  expect_null(get_session_greeting_state(spy$session, "chat"))
})

test_that("restore_greeting_snapshot() rejects an invalid content_type", {
  spy <- mock_session_with_spy()
  snapshot <- list(
    content = "Hello",
    content_type = "evil",
    options = list(),
    html_deps = list()
  )
  expect_error(
    restore_greeting_snapshot("chat", snapshot, session = spy$session),
    "invalid or missing"
  )
  expect_null(get_session_greeting_state(spy$session, "chat"))
})

test_that("restore_greeting_snapshot() rejects a malformed html_deps entry", {
  spy <- mock_session_with_spy()
  snapshot <- list(
    content = "Hello",
    content_type = "markdown",
    options = list(),
    html_deps = list(list(name = "greeting-style"))
  )
  expect_error(
    restore_greeting_snapshot("chat", snapshot, session = spy$session),
    "invalid or missing"
  )
  expect_null(get_session_greeting_state(spy$session, "chat"))
})

test_that("chat_set_greeting() errors when given a function", {
  spy <- mock_session_with_spy()
  shiny::withReactiveDomain(spy$session, {
    expect_error(
      chat_set_greeting("chat", function() "hi", session = spy$session),
      "does not accept a function"
    )
  })
})

# ── chat_clear() greeting parameter ─────────────────────────────────────────

test_that("chat_clear() sends clear action without greeting field by default", {
  spy <- mock_session_with_spy()
  shiny::withReactiveDomain(spy$session, {
    chat_clear("chat", session = spy$session)
  })
  msgs <- spy_messages(spy)
  expect_length(msgs, 1)
  action <- msgs[[1]]$message$action
  expect_equal(action$type, "clear")
  expect_null(action$greeting)
})

test_that("chat_clear(greeting = TRUE) includes greeting in action", {
  spy <- mock_session_with_spy()
  shiny::withReactiveDomain(spy$session, {
    chat_clear("chat", greeting = TRUE, session = spy$session)
  })
  msgs <- spy_messages(spy)
  expect_length(msgs, 1)
  action <- msgs[[1]]$message$action
  expect_equal(action$type, "clear")
  expect_true(action$greeting)
})

# ── chat_server() greeting function ──────────────────────────────────────────

# Helper: minimal R6 mock that satisfies check_ellmer_chat() and chat_restore().
# Requires get_tools() so that the chat_restore set_ui observer does not crash
# and block subsequent observers.
mock_chat_client <- function(turns = list()) {
  R6::R6Class(
    "Chat",
    cloneable = TRUE,
    public = list(
      turns = turns,
      set_turns = function(t) {
        self$turns <- t
        invisible(self)
      },
      get_turns = function() self$turns,
      get_tools = function() list(),
      last_turn = function() NULL
    )
  )$new()
}

# Helper: suppress expected warnings from chat_restore()'s set_ui observer,
# which calls into ellmer internals not available on the mock client.
suppress_restore_warnings <- function(expr) {
  withCallingHandlers(
    expr,
    warning = function(w) {
      # Suppress expected warnings/errors from chat_restore's set_ui observer,
      # which calls ellmer internals not implemented on the mock client.
      if (
        grepl(
          "non-function|set_ui|tools|no applicable method",
          conditionMessage(w)
        )
      ) {
        invokeRestart("muffleWarning")
      }
    }
  )
}

test_that("named-arg detection: 'client' in formals identifies one-arg greeting", {
  expect_true(
    "client" %in%
      names(
        formals(function(client) {})
      )
  )
  expect_false(
    "client" %in%
      names(
        formals(function() {})
      )
  )
  expect_false(
    "client" %in%
      names(
        formals(function(x) {})
      )
  )
})

test_that("chat_server() calls zero-arg greeting on chat_greeting_requested", {
  called <- FALSE
  client <- mock_chat_client()
  greeting <- function() {
    called <<- TRUE
    "## Hello"
  }
  suppress_restore_warnings(
    shiny::testServer(
      function(input, output, session) {
        chat_server("chat", client, greeting = greeting, session = session)
      },
      {
        expect_false(called)
        session$setInputs(chat_greeting_requested = 1L)
        expect_true(called)
      }
    )
  )
})

test_that("chat_server() zero-arg greeting is not called without input trigger", {
  called <- FALSE
  client <- mock_chat_client()
  greeting <- function() {
    called <<- TRUE
    "## Hello"
  }
  suppress_restore_warnings(
    shiny::testServer(
      function(input, output, session) {
        chat_server("chat", client, greeting = greeting, session = session)
      },
      {
        # No setInputs — observer must not fire
        expect_false(called)
      }
    )
  )
})

test_that("chat_server() calls one-arg greeting with a cloned client on chat_greeting_requested", {
  received_greeter <- NULL
  client <- mock_chat_client()
  greeting <- function(client) {
    received_greeter <<- client
    "## Hello"
  }
  suppress_restore_warnings(
    shiny::testServer(
      function(input, output, session) {
        chat_server("chat", client, greeting = greeting, session = session)
      },
      {
        session$setInputs(chat_greeting_requested = 1L)
        expect_true(inherits(received_greeter, "Chat"))
      }
    )
  )
})

test_that("chat_server() one-arg greeting receives a client with empty turns", {
  received_turns <- NULL
  client_with_turns <- mock_chat_client()
  client_with_turns$set_turns(
    list(
      list(
        role = "user",
        content = "prior message"
      )
    )
  )
  greeting <- function(client) {
    received_turns <<- client$get_turns()
    "## Hello"
  }
  suppress_restore_warnings(
    shiny::testServer(
      function(input, output, session) {
        chat_server(
          "chat",
          client_with_turns,
          greeting = greeting,
          session = session
        )
      },
      {
        session$setInputs(chat_greeting_requested = 1L)
        expect_equal(length(received_turns), 0L)
      }
    )
  )
})

test_that("chat_server() one-arg greeting does not clear original client turns", {
  client_with_turns <- mock_chat_client()
  client_with_turns$set_turns(
    list(
      list(
        role = "user",
        content = "prior message"
      )
    )
  )
  suppress_restore_warnings(
    shiny::testServer(
      function(input, output, session) {
        chat_server(
          "chat",
          client_with_turns,
          greeting = function(client) "## Hello",
          session = session
        )
      },
      {
        session$setInputs(chat_greeting_requested = 1L)
        expect_equal(length(client_with_turns$get_turns()), 1L)
      }
    )
  )
})

test_that("chat_server() does not error with static string greeting", {
  client <- mock_chat_client()
  expect_no_error(
    suppress_restore_warnings(
      shiny::testServer(
        function(input, output, session) {
          chat_server("chat", client, greeting = "## Static", session = session)
        },
        {}
      )
    )
  )
})

# ── chat_restore() bookmark exclusions ───────────────────────────────────────

mock_session_with_bookmark_spy <- function() {
  shiny::MockShinySession$new()
}

test_that("chat_restore() excludes {id}_greeting_requested from bookmarking", {
  sess <- mock_session_with_bookmark_spy()
  suppress_restore_warnings(
    shiny::withReactiveDomain(sess, {
      chat_restore(
        "chat",
        mock_chat_client(),
        bookmark_on_input = FALSE,
        bookmark_on_response = FALSE,
        session = sess
      )
    })
  )
  expect_true("chat_greeting_requested" %in% sess$getBookmarkExclude())
})

test_that("chat_clear() with greeting=TRUE clears session greeting state", {
  sess <- shiny::MockShinySession$new()

  set_session_greeting_state(sess, "chat", list(content = "Hello"))
  expect_equal(get_session_greeting_state(sess, "chat")$content, "Hello")

  shiny::withReactiveDomain(sess, {
    chat_clear("chat", greeting = TRUE, session = sess)
  })

  expect_null(get_session_greeting_state(sess, "chat"))
})

test_that("chat_get_greeting() returns NULL when no greeting is set", {
  sess <- shiny::MockShinySession$new()
  shiny::withReactiveDomain(sess, {
    expect_null(chat_get_greeting("chat", session = sess))
  })
})

test_that("chat_get_greeting() returns content after chat_set_greeting()", {
  sess <- shiny::MockShinySession$new()
  set_session_greeting_state(sess, "chat", list(content = "Hello!"))
  shiny::withReactiveDomain(sess, {
    expect_equal(chat_get_greeting("chat", session = sess), "Hello!")
  })
})

test_that("chat_restore() excludes {id}_greeting_dismissed from bookmarking", {
  sess <- mock_session_with_bookmark_spy()
  suppress_restore_warnings(
    shiny::withReactiveDomain(sess, {
      chat_restore(
        "chat",
        mock_chat_client(),
        bookmark_on_input = FALSE,
        bookmark_on_response = FALSE,
        session = sess
      )
    })
  )
  expect_true("chat_greeting_dismissed" %in% sess$getBookmarkExclude())
})

# ── chat_restore() bookmark save/restore round-trips the full snapshot ──────

# MockShinySession$onBookmark()/onRestore() are no-ops, so intercept the
# registered callbacks directly instead of driving a real bookmark cycle.
# `chat_restore()` registers the client hook first and the greeting hook
# second for both onBookmark() and onRestore(); index into that fixed order.
mock_session_with_bookmark_hooks <- function() {
  sess <- shiny::MockShinySession$new()
  spy_env <- new.env(parent = emptyenv())
  spy_env$messages <- list()
  spy_env$on_bookmark <- list()
  spy_env$on_restore <- list()
  sess$sendCustomMessage <- function(type, msg) {
    spy_env$messages[[length(spy_env$messages) + 1]] <- list(
      type = type,
      message = msg
    )
  }
  sess$onBookmark <- function(fun) {
    spy_env$on_bookmark[[length(spy_env$on_bookmark) + 1]] <- fun
    function() invisible(NULL)
  }
  sess$onRestore <- function(fun) {
    spy_env$on_restore[[length(spy_env$on_restore) + 1]] <- fun
    function() invisible(NULL)
  }
  list(session = sess, spy_env = spy_env)
}

new_bookmark_state <- function(values = list()) {
  state <- new.env(parent = emptyenv())
  state$values <- values
  state
}

test_that("chat_restore() bookmark save writes the full greeting snapshot", {
  spy <- mock_session_with_bookmark_hooks()
  sess <- spy$session
  snapshot <- list(
    content = "<strong>Welcome</strong>",
    content_type = "html",
    options = list(persistent = TRUE),
    html_deps = list()
  )
  set_session_greeting_state(sess, "chat", snapshot)

  suppress_restore_warnings(
    shiny::withReactiveDomain(sess, {
      chat_restore(
        "chat",
        mock_chat_client(),
        bookmark_on_input = FALSE,
        bookmark_on_response = FALSE,
        session = sess
      )
    })
  )

  state <- new_bookmark_state()
  spy$spy_env$on_bookmark[[2]](state)

  expect_identical(state$values[["chat_greeting"]], snapshot)
})

test_that("chat_restore() bookmark restore sends the original recipe and passes html_deps", {
  spy <- mock_session_with_bookmark_hooks()
  sess <- spy$session
  snapshot <- list(
    content = "<strong>Welcome</strong>",
    content_type = "html",
    options = list(persistent = TRUE),
    html_deps = list(list(name = "greeting-style", version = "1.0.0"))
  )

  suppress_restore_warnings(
    shiny::withReactiveDomain(sess, {
      chat_restore(
        "chat",
        mock_chat_client(),
        bookmark_on_input = FALSE,
        bookmark_on_response = FALSE,
        session = sess
      )
    })
  )

  state <- new_bookmark_state(list(chat_greeting = snapshot))
  shiny::withReactiveDomain(sess, {
    spy$spy_env$on_restore[[2]](state)
  })

  msgs <- spy_messages(spy)
  greeting_msgs <- Filter(
    function(m) identical(m$message$action$type, "greeting"),
    msgs
  )
  expect_length(greeting_msgs, 1)
  expect_identical(
    greeting_msgs[[1]]$message$action,
    list(
      type = "greeting",
      content = snapshot$content,
      content_type = snapshot$content_type,
      options = snapshot$options
    )
  )
  expect_identical(greeting_msgs[[1]]$message$html_deps, snapshot$html_deps)
  expect_identical(get_session_greeting_state(sess, "chat"), snapshot)
})

test_that("chat_restore() bookmark restore rejects content-only legacy greeting state", {
  spy <- mock_session_with_bookmark_hooks()
  sess <- spy$session

  suppress_restore_warnings(
    shiny::withReactiveDomain(sess, {
      chat_restore(
        "chat",
        mock_chat_client(),
        bookmark_on_input = FALSE,
        bookmark_on_response = FALSE,
        session = sess
      )
    })
  )

  state <- new_bookmark_state(list(chat_greeting = list(content = "Hello")))
  expect_error(
    shiny::withReactiveDomain(sess, {
      spy$spy_env$on_restore[[2]](state)
    }),
    "invalid or missing"
  )
})
