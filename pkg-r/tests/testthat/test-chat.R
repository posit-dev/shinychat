library(htmltools)

test_that("Chat component markup", {
  expect_snapshot(chat_ui("chat"))

  expect_snapshot({
    chat_ui("chat", messages = list("Foo", "Bar"))
  })

  expect_snapshot({
    chat_ui(
      "chat",
      messages = list(
        list(content = "Assistant", role = "assistant"),
        list(content = "User", role = "user")
      )
    )
  })

  expect_snapshot({
    chat_ui(
      "chat",
      messages = list(
        div("Hello"),
        span("world")
      )
    )
  })

  expect_snapshot({
    render_tags(
      chat_ui(
        "chat",
        messages = list(
          div("Hello", htmlDependency("foo", "1.0.0", "")),
          span("world")
        )
      )
    )
  })

  # Initial messages with react elements are island-split
  expect_snapshot({
    react_tag <- tags$div("react", `data-shinychat-react` = NA)
    chat_ui(
      "chat",
      messages = list(
        tagList(tags$div("before"), react_tag, tags$div("after"))
      )
    )
  })

  # TODO: it'd be nice to mock the shinyChatMessage custom messages
})

test_that("chat_ui configures derived aside favicons from the environment", {
  withr::local_envvar(list(SHINYCHAT_ASIDE_FAVICON = NULL))
  expect_no_match(as.character(chat_ui("chat")), "aside-favicon", fixed = TRUE)

  Sys.setenv(SHINYCHAT_ASIDE_FAVICON = "false")
  expect_match(
    as.character(chat_ui("chat")),
    'aside-favicon="false"',
    fixed = TRUE
  )

  Sys.setenv(SHINYCHAT_ASIDE_FAVICON = "TrUe")
  expect_no_match(as.character(chat_ui("chat")), "aside-favicon", fixed = TRUE)

  Sys.setenv(SHINYCHAT_ASIDE_FAVICON = "sometimes")
  expect_error(chat_ui("chat"), "SHINYCHAT_ASIDE_FAVICON")
})

test_that("chat_ui() emits tool-grouping only when non-default", {
  ui_default <- chat_ui("chat")
  expect_null(ui_default$attribs[["tool-grouping"]])

  ui_tool <- chat_ui("chat", tool_grouping = "tool")
  expect_null(ui_tool$attribs[["tool-grouping"]])

  ui_all <- chat_ui("chat", tool_grouping = "all")
  expect_equal(ui_all$attribs[["tool-grouping"]], "all")

  ui_none <- chat_ui("chat", tool_grouping = "none")
  expect_equal(ui_none$attribs[["tool-grouping"]], "none")

  expect_snapshot(chat_ui("chat", tool_grouping = "all"))
})

test_that("chat_ui() errors for an invalid tool_grouping value", {
  expect_snapshot(
    error = TRUE,
    chat_ui("chat", tool_grouping = "invalid")
  )
})

test_that("chat_ui(icon_assistant = FALSE) removes the icon", {
  # FALSE removes the icon: the container and each message carry icon="".
  ui <- chat_ui("chat", messages = list("Hello"), icon_assistant = FALSE)
  expect_equal(ui$attribs[["icon-assistant"]], "")

  html <- as.character(ui)
  expect_match(html, 'icon-assistant=""', fixed = TRUE)
  expect_match(html, 'icon=""', fixed = TRUE)
})

test_that("chat_ui(icon_assistant = TRUE/NULL) omits the icon attribute", {
  ui_true <- chat_ui("chat", messages = list("Hello"), icon_assistant = TRUE)
  expect_null(ui_true$attribs[["icon-assistant"]])
  expect_no_match(as.character(ui_true), "icon-assistant", fixed = TRUE)

  ui_null <- chat_ui("chat", messages = list("Hello"))
  expect_null(ui_null$attribs[["icon-assistant"]])
  expect_no_match(as.character(ui_null), "icon-assistant", fixed = TRUE)
})

test_that("chat_ui() does not put the assistant icon on user messages", {
  # User messages render `icon` directly, so the assistant default must not be
  # copied onto them (it would misattribute who said what).
  ui <- chat_ui(
    "chat",
    messages = list(
      list(role = "user", content = "Hi"),
      list(role = "assistant", content = "Hello")
    ),
    icon_assistant = htmltools::HTML("<span>ROBOT</span>")
  )

  msgs <- strsplit(as.character(ui), "<shiny-chat-message ")[[1]]
  expect_match(msgs[[2]], 'data-role="user"')
  expect_false(grepl("ROBOT", msgs[[2]], fixed = TRUE))
  expect_match(msgs[[3]], 'data-role="assistant"')
  expect_true(grepl("ROBOT", msgs[[3]], fixed = TRUE))
})

test_that("resolve_icon_attr() translates the boolean sentinel", {
  expect_null(resolve_icon_attr(NULL))
  expect_null(resolve_icon_attr(TRUE))
  expect_equal(resolve_icon_attr(FALSE), "")
  expect_equal(resolve_icon_attr("<span>x</span>"), "<span>x</span>")
})

test_that("chat_append_stream() returns the stream contents as string if all text", {
  local_mocked_bindings(
    chat_append_message = coro::async(function(...) invisible())
  )

  stream <- coro::async_generator(function() {
    for (i in c("Hello", ",", " world", "!")) {
      yield(i)
    }
  })

  p <- chat_append_stream("chat", stream())
  res <- sync(p)

  expect_promise(p, "fulfilled")
  expect_equal(res, "Hello, world!")
})

test_that("chat_append_stream() returns the stream contents as list if not all text", {
  local_mocked_bindings(
    chat_append_message = coro::async(function(...) invisible())
  )

  stream <- coro::async_generator(function() {
    for (i in c("Hello", ",", " world", "!")) {
      yield(ellmer::ContentText(i))
    }
  })

  p <- chat_append_stream("chat", stream())
  res <- sync(p)

  expect_promise(p, "fulfilled")

  expect_true(is.list(res))
  expect_true(every(res, inherits, "ellmer::ContentText"))
  expect_equal(
    paste(map_chr(res, ellmer::contents_text), collapse = ""),
    "Hello, world!"
  )
})

test_that("chat_append_stream() handles errors in the stream", {
  local_mocked_bindings(
    chat_append_message = coro::async(function(...) invisible())
  )

  shiny::withReactiveDomain(shiny::MockShinySession$new(), {
    stream <- coro::async_generator(function() {
      for (i in 1:3) {
        yield(i)
      }
      stop("boom")
    })

    p <- chat_append_stream("chat", stream())
    expect_warning(
      res <- tryCatch(sync(p), error = identity),
      regexp = 'chat_append_stream'
    )

    expect_promise(p, "rejected")

    expect_s3_class(res, class = c("condition", "error"))
    expect_s3_class(res, class = "shiny.silent.error")
    expect_equal(conditionMessage(res), "boom")
  })
})

test_that("chat_append_stream() settles a sanitized error before rejecting", {
  withr::local_options(shiny.sanitize.errors = TRUE)
  local_mocked_bindings(
    send_chat_action = function(...) invisible(NULL)
  )
  session <- shiny::MockShinySession$new()
  transcript <- register_chat_transcript(session, "chat")
  state_on_rejection <- NULL

  stream <- coro::async_generator(function() {
    yield("partial")
    stop("secret failure")
  })

  p <- chat_append_stream("chat", stream(), session = session)
  observed <- promises::catch(p, function(reason) {
    state_on_rejection <<- transcript$read()
    NULL
  })
  expect_warning(
    sync(observed),
    regexp = "chat_append_stream"
  )

  expect_promise(p, "rejected")
  expect_identical(
    state_on_rejection,
    list(
      list(
        role = "assistant",
        segments = list(
          list(
            content = paste0(
              "partial\n\n**An error occurred. ",
              "Please try again or contact the app author.**"
            ),
            content_type = "markdown"
          )
        )
      )
    )
  )
})

test_that("a cleared stream cannot write into or settle its replacement", {
  deferred_promise <- function() {
    resolve_deferred <- NULL
    promise <- promises::promise(function(resolve, reject) {
      resolve_deferred <<- resolve
    })
    list(
      promise = promise,
      resolve = function(value) resolve_deferred(value)
    )
  }

  session <- shiny::MockShinySession$new()
  transcript <- register_chat_transcript(session, "chat")
  actions <- list()
  local_mocked_bindings(
    send_chat_action = function(id, action, html_deps = NULL, session) {
      actions[[length(actions) + 1L]] <<- action
      invisible(NULL)
    }
  )

  deferred_a <- deferred_promise()
  stream_a <- coro::async_generator(function() {
    yield(deferred_a$promise)
  })
  result_a <- chat_append_stream("chat", stream_a(), session = session)

  chat_clear("chat", session = session)

  deferred_b <- deferred_promise()
  stream_b <- coro::async_generator(function() {
    yield(deferred_b$promise)
  })
  result_b <- chat_append_stream("chat", stream_b(), session = session)
  actions_before_stale_chunk <- actions

  deferred_a$resolve("stale")
  sync(result_a)

  expect_identical(actions, actions_before_stale_chunk)
  expect_identical(transcript$read(), list())

  deferred_b$resolve("fresh")
  expect_identical(sync(result_b), "fresh")
  expect_identical(
    vapply(actions, `[[`, character(1), "type"),
    c("chunk_start", "clear", "chunk_start", "chunk", "chunk_end")
  )
  expect_identical(
    transcript$read(),
    list(
      list(
        role = "assistant",
        segments = list(list(content = "fresh", content_type = "markdown"))
      )
    )
  )
})

test_that("an error-render send failure preserves the original rejection", {
  original_marker <- new.env(parent = emptyenv())
  original <- structure(
    list(
      message = "original stream failure",
      call = NULL,
      marker = original_marker
    ),
    class = c("stream_original_error", "error", "condition")
  )
  warnings <- list()
  local_mocked_bindings(
    send_chat_action = function(id, action, html_deps = NULL, session) {
      if (
        identical(action$type, "chunk") &&
          grepl("An error occurred", action$content, fixed = TRUE)
      ) {
        rlang::abort("error render send failed")
      }
      invisible(NULL)
    }
  )
  session <- shiny::MockShinySession$new()
  stream <- coro::async_generator(function() {
    yield("partial")
    stop(original)
  })

  result <- withCallingHandlers(
    tryCatch(
      sync(chat_append_stream("chat", stream(), session = session)),
      error = identity
    ),
    warning = function(warning) {
      warnings[[length(warnings) + 1L]] <<- warning
      invokeRestart("muffleWarning")
    }
  )

  expect_s3_class(result, "stream_original_error")
  expect_identical(result$marker, original_marker)
  expect_identical(conditionMessage(result), "original stream failure")
  expect_match(
    paste(vapply(warnings, conditionMessage, character(1)), collapse = "\n"),
    "error render send failed",
    fixed = TRUE
  )
})

test_that("chat_server handles string user_input values", {
  local_mocked_bindings(
    chat_restore = function(...) function() invisible(NULL),
    chat_append = function(...) invisible(NULL),
    send_chat_action = function(...) invisible(NULL)
  )

  args_seen <- NULL
  client <- structure(
    list(
      stream_async = function(...) {
        args_seen <<- rlang::list2(...)
        NULL
      },
      last_turn = function() NULL
    ),
    class = "Chat"
  )

  shiny::testServer(
    function(input, output, session) {
      chat_server(
        "chat",
        client,
        history = FALSE,
        session = session
      )
    },
    {
      expect_no_warning(session$setInputs(chat_user_input = "hello"))
      expect_identical(args_seen[[1]], "hello")
    }
  )
})

test_that("chat_server warns when bookmark_on_input is used", {
  local_mocked_bindings(
    chat_restore = function(...) invisible(NULL),
    send_chat_action = function(...) invisible(NULL)
  )

  client <- structure(list(), class = "Chat")

  shiny::testServer(
    function(input, output, session) {
      lifecycle::expect_deprecated(
        chat_server(
          "chat",
          client,
          history = FALSE,
          bookmark_on_input = TRUE,
          session = session
        ),
        "bookmark_on_input"
      )
    },
    {}
  )
})

test_that("chat_server warns when bookmark_on_response is used", {
  local_mocked_bindings(
    chat_restore = function(...) invisible(NULL),
    send_chat_action = function(...) invisible(NULL)
  )

  client <- structure(list(), class = "Chat")

  shiny::testServer(
    function(input, output, session) {
      lifecycle::expect_deprecated(
        chat_server(
          "chat",
          client,
          history = FALSE,
          bookmark_on_response = TRUE,
          session = session
        ),
        "bookmark_on_response"
      )
    },
    {}
  )
})

test_that("chat_append_message() emits segment payloads incl. thinking", {
  captured <- list()
  local_mocked_bindings(
    send_chat_action = function(id, action, html_deps = NULL, session) {
      captured[[length(captured) + 1]] <<- action
      invisible()
    }
  )
  session <- shiny::MockShinySession$new()

  chat_append_message(
    "chat",
    list(role = "assistant", content = "hello"),
    chunk = FALSE,
    session = session
  )
  chat_append_message(
    "chat",
    list(role = "assistant", content = ""),
    chunk = "start",
    session = session
  )
  th <- structure("reasoning", class = "shinychat_thinking")
  chat_append_message(
    "chat",
    list(role = "assistant", content = th),
    chunk = TRUE,
    session = session
  )

  msg <- captured[[1]]
  expect_equal(msg$type, "message")
  expect_null(msg$message$content)
  expect_equal(msg$message$segments[[1]]$content, "hello")
  expect_equal(msg$message$segments[[1]]$content_type, "markdown")

  chunk <- captured[[3]]
  expect_equal(chunk$content_type, "thinking")
})

test_that("chat_append_message() sends complete messages before committing", {
  session <- shiny::MockShinySession$new()
  transcript <- register_chat_transcript(session, "chat")
  state_during_send <- NULL
  local_mocked_bindings(
    send_chat_action = function(...) {
      state_during_send <<- transcript$read()
      invisible(NULL)
    }
  )

  chat_append_message(
    "chat",
    list(role = "assistant", content = "Hi"),
    chunk = FALSE,
    session = session
  )

  expect_identical(state_during_send, list())
  expect_identical(
    transcript$read(),
    list(
      list(
        role = "assistant",
        segments = list(list(content = "Hi", content_type = "markdown"))
      )
    )
  )
})

test_that("chat_append_message() does not commit failed complete sends", {
  session <- shiny::MockShinySession$new()
  transcript <- register_chat_transcript(session, "chat")
  local_mocked_bindings(
    send_chat_action = function(...) rlang::abort("send failed")
  )

  expect_error(
    chat_append_message(
      "chat",
      list(role = "assistant", content = "Hi"),
      chunk = FALSE,
      session = session
    ),
    "send failed",
    fixed = TRUE
  )
  expect_identical(transcript$read(), list())
})

test_that("chat_append_message() commits streamed append, replace, and end sends", {
  session <- shiny::MockShinySession$new()
  transcript <- register_chat_transcript(session, "chat")
  actions <- list()
  local_mocked_bindings(
    send_chat_action = function(id, action, html_deps = NULL, session) {
      actions[[length(actions) + 1L]] <<- action
      invisible(NULL)
    }
  )

  chat_append_message(
    "chat",
    list(role = "assistant", content = ""),
    chunk = "start",
    session = session
  )
  chat_append_message(
    "chat",
    list(role = "assistant", content = "draft"),
    session = session
  )
  chat_append_message(
    "chat",
    list(role = "assistant", content = "final"),
    chunk = "end",
    operation = "replace",
    session = session
  )

  expect_identical(
    vapply(actions, `[[`, character(1), "type"),
    c("chunk_start", "chunk", "chunk", "chunk_end")
  )
  expect_identical(actions[[4L]], list(type = "chunk_end"))
  expect_identical(
    transcript$read(),
    list(
      list(
        role = "assistant",
        segments = list(list(content = "final", content_type = "markdown"))
      )
    )
  )
})

test_that("chat_append_message() excludes a stream chunk whose send fails", {
  session <- shiny::MockShinySession$new()
  transcript <- register_chat_transcript(session, "chat")
  local_mocked_bindings(
    send_chat_action = function(id, action, html_deps = NULL, session) {
      if (identical(action$content, "lost")) {
        rlang::abort("send failed")
      }
      invisible(NULL)
    }
  )

  chat_append_message(
    "chat",
    list(role = "assistant", content = ""),
    chunk = "start",
    session = session
  )
  expect_error(
    chat_append_message(
      "chat",
      list(role = "assistant", content = "lost"),
      session = session
    ),
    "send failed",
    fixed = TRUE
  )
  chat_append_message(
    "chat",
    list(role = "assistant", content = "kept"),
    chunk = "end",
    session = session
  )

  expect_identical(
    transcript$read()[[1]]$segments[[1]]$content,
    "kept"
  )
})

test_that("chat_clear() clears only after its send succeeds", {
  session <- shiny::MockShinySession$new()
  transcript <- register_chat_transcript(session, "chat")
  fail_send <- FALSE
  local_mocked_bindings(
    send_chat_action = function(...) {
      if (fail_send) {
        rlang::abort("send failed")
      }
      invisible(NULL)
    }
  )

  chat_append_message(
    "chat",
    list(role = "assistant", content = "keep"),
    chunk = FALSE,
    session = session
  )

  fail_send <- TRUE
  expect_error(
    chat_clear("chat", session = session),
    "send failed",
    fixed = TRUE
  )
  expect_identical(
    transcript$read()[[1]]$segments[[1]]$content,
    "keep"
  )

  fail_send <- FALSE
  chat_clear("chat", session = session)
  expect_identical(transcript$read(), list())
})

test_that("standalone appends send without registering transcript state", {
  session <- shiny::MockShinySession$new()
  actions <- list()
  local_mocked_bindings(
    send_chat_action = function(id, action, html_deps = NULL, session) {
      actions[[length(actions) + 1L]] <<- action
    }
  )

  chat_append_message(
    "chat",
    list(role = "assistant", content = "display only"),
    chunk = FALSE,
    session = session
  )

  expect_length(actions, 1L)
  expect_null(get_chat_transcript(session, "chat"))
})

test_that("standalone chat_append_stream() sends actions but leaves no transcript", {
  session <- shiny::MockShinySession$new()
  actions <- list()
  local_mocked_bindings(
    send_chat_action = function(id, action, html_deps = NULL, session) {
      actions[[length(actions) + 1L]] <<- action
      invisible(NULL)
    }
  )
  stream <- coro::async_generator(function() {
    yield("standalone")
  })

  res <- sync(chat_append_stream("chat", stream(), session = session))

  expect_equal(res, "standalone")
  expect_true(length(actions) > 0)
  expect_null(get_chat_transcript(session, "chat"))
})

test_that("standalone chat_clear() sends the clear action without creating transcript state", {
  session <- shiny::MockShinySession$new()
  actions <- list()
  local_mocked_bindings(
    send_chat_action = function(id, action, html_deps = NULL, session) {
      actions[[length(actions) + 1L]] <<- action
      invisible(NULL)
    }
  )

  chat_clear("chat", session = session)

  expect_identical(actions, list(list(type = "clear")))
  expect_null(get_chat_transcript(session, "chat"))
})
