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

test_that("chat_ui() renders toolbar_input and footer islands", {
  ui <- chat_ui(
    "chat",
    toolbar_input = htmltools::tags$span("Toolbar input"),
    footer = htmltools::tags$span("Footer")
  )
  html <- as.character(ui)

  expect_match(html, "<shiny-chat-input-toolbar>", fixed = TRUE)
  expect_match(html, "Toolbar input", fixed = TRUE)
  expect_match(html, "<shiny-chat-footer>", fixed = TRUE)
  expect_match(html, "Footer", fixed = TRUE)
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

test_that("chat_ui(icon_assistant = TRUE) omits the icon attribute", {
  ui_true <- chat_ui("chat", messages = list("Hello"), icon_assistant = TRUE)
  expect_null(ui_true$attribs[["icon-assistant"]])
  expect_no_match(as.character(ui_true), "icon-assistant", fixed = TRUE)
})

test_that("chat_ui(icon_assistant = NULL) (the default) removes the icon", {
  ui_null <- chat_ui("chat", messages = list("Hello"))
  expect_equal(ui_null$attribs[["icon-assistant"]], "")

  html <- as.character(ui_null)
  expect_match(html, 'icon-assistant=""', fixed = TRUE)
  expect_match(html, 'icon=""', fixed = TRUE)
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

test_that("chat_ui(icon_send = ...) sets the icon-send attribute", {
  ui <- chat_ui("chat", icon_send = htmltools::HTML("<span>UP</span>"))
  expect_equal(ui$attribs[["icon-send"]], "<span>UP</span>")
  expect_match(
    as.character(ui),
    'icon-send="&lt;span&gt;UP&lt;/span&gt;"',
    fixed = TRUE
  )
})

test_that("chat_ui(icon_send = FALSE/NULL) omits the icon-send attribute", {
  for (icon_send in list(NULL, FALSE)) {
    ui <- chat_ui("chat", icon_send = icon_send)
    expect_null(ui$attribs[["icon-send"]])
    expect_no_match(as.character(ui), "icon-send", fixed = TRUE)
  }
})

test_that("chat_ui(icon_send = TRUE) is rejected", {
  expect_error(chat_ui("chat", icon_send = TRUE), "does not accept `TRUE`")
})

test_that("resolve_send_icon_attr() has no blank/FALSE state", {
  expect_null(resolve_send_icon_attr(NULL))
  expect_null(resolve_send_icon_attr(FALSE))
  expect_error(resolve_send_icon_attr(TRUE), "does not accept `TRUE`")
  expect_equal(resolve_send_icon_attr("<span>x</span>"), "<span>x</span>")
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

test_that("chat_append_stream() handles a stream that fails before it yields", {
  messages <- list()
  local_mocked_bindings(
    chat_append_message = function(
      id,
      msg,
      chunk = TRUE,
      operation = c("append", "replace"),
      icon = NULL,
      session = getDefaultReactiveDomain()
    ) {
      messages[[length(messages) + 1]] <<- list(
        id = id,
        msg = msg,
        chunk = chunk,
        operation = operation
      )
      invisible()
    }
  )
  withr::local_options(shiny.sanitize.errors = TRUE)

  shiny::withReactiveDomain(shiny::MockShinySession$new(), {
    # A synchronous generator, the shape `ellmer::Chat$stream_async()` returns:
    # the request runs on first advance, so a provider that rejects the turn
    # outright throws before the coroutine reaches its first `await`.
    stream <- coro::generator(function() {
      stop("boom")
      yield(1)
    })

    p <- chat_append_stream("chat", stream())
    expect_warning(
      res <- tryCatch(sync(p), error = identity),
      regexp = "chat_append_stream"
    )

    expect_promise(p, "rejected")
    expect_equal(conditionMessage(res), "boom")
    expect_s3_class(res, "shiny.silent.error")
    expect_length(messages, 2)
    expect_equal(
      messages[[2]],
      list(
        id = "chat",
        msg = list(
          role = "assistant",
          content = paste0(
            "\n\n**An error occurred. Please try again or contact ",
            "the app author.**"
          )
        ),
        chunk = "end",
        operation = "append"
      )
    )
  })
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
      later::run_now(0.05)
      session$flushReact()
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

  chunk <- captured[[2]]
  expect_equal(chunk$content_type, "thinking")
})

test_that("chat_append_message() non-streaming message carries inline mixed segments", {
  captured <- list()
  local_mocked_bindings(
    send_chat_action = function(id, action, html_deps = NULL, session) {
      captured[[length(captured) + 1]] <<- list(
        action = action,
        html_deps = html_deps
      )
      invisible()
    }
  )
  session <- shiny::MockShinySession$new()

  # Build a tool_request block and a tool_result block
  req_block <- new_tool_card(
    "tool_request",
    request_id = "req-1",
    tool_name = "get_weather",
    intent = "Check weather",
    arguments = '{"location": "NYC"}'
  )
  res_block <- structure(
    list(
      type = "tool_result",
      version = 1L,
      request_id = "req-1",
      tool_name = "get_weather",
      status = "success",
      value = "Sunny, 72F",
      value_type = "markdown"
    ),
    class = c("shinychat_tool_result", "shinychat_block")
  )

  # Non-streaming: chunk = FALSE emits a single "message" action with
  # inline segments preserving order: string, block, string, block
  chat_append_message(
    "chat",
    list(
      role = "assistant",
      content = list("Hello ", req_block, " world ", res_block)
    ),
    chunk = FALSE,
    session = session
  )

  expect_length(captured, 1)
  msg <- captured[[1]]$action
  expect_equal(msg$type, "message")
  expect_equal(msg$message$role, "assistant")

  segments <- msg$message$segments
  expect_length(segments, 4)

  # Segment 1: string -> markdown
  expect_equal(segments[[1]]$content, "Hello ")
  expect_equal(segments[[1]]$content_type, "markdown")

  # Segment 2: tool_request block
  expect_equal(segments[[2]]$type, "tool_request")
  expect_equal(segments[[2]]$request_id, "req-1")
  expect_equal(segments[[2]]$tool_name, "get_weather")

  # Segment 3: string -> markdown
  expect_equal(segments[[3]]$content, " world ")
  expect_equal(segments[[3]]$content_type, "markdown")

  # Segment 4: tool_result block
  expect_equal(segments[[4]]$type, "tool_result")
  expect_equal(segments[[4]]$request_id, "req-1")
  expect_equal(segments[[4]]$status, "success")
  expect_equal(segments[[4]]$value, "Sunny, 72F")
})

test_that("chat_append_message() streaming emits chunk_start, interleaved chunk/block_insert, chunk_end", {
  captured <- list()
  local_mocked_bindings(
    send_chat_action = function(id, action, html_deps = NULL, session) {
      captured[[length(captured) + 1]] <<- list(
        action = action,
        html_deps = html_deps
      )
      invisible()
    }
  )
  session <- shiny::MockShinySession$new()

  req_block <- new_tool_card(
    "tool_request",
    request_id = "req-s1",
    tool_name = "search",
    intent = "Search",
    arguments = '{"q": "shiny"}'
  )
  res_block <- structure(
    list(
      type = "tool_result",
      version = 1L,
      request_id = "req-s1",
      tool_name = "search",
      status = "success",
      value = "Found 3 results",
      value_type = "markdown"
    ),
    class = c("shinychat_tool_result", "shinychat_block")
  )

  # chunk = "start": carries the full message payload with inline segments
  chat_append_message(
    "chat",
    list(
      role = "assistant",
      content = list("Starting ", req_block)
    ),
    chunk = "start",
    session = session
  )

  # chunk = TRUE (intermediate): emit each segment in order
  chat_append_message(
    "chat",
    list(
      role = "assistant",
      content = list(" processing ", res_block)
    ),
    chunk = TRUE,
    session = session
  )

  # chunk = "end": emit remaining segments, then chunk_end
  chat_append_message(
    "chat",
    list(role = "assistant", content = list(" done")),
    chunk = "end",
    session = session
  )

  # chunk_start
  expect_equal(captured[[1]]$action$type, "chunk_start")
  expect_equal(captured[[1]]$action$message$role, "assistant")
  expect_length(captured[[1]]$action$message$segments, 2)
  expect_equal(captured[[1]]$action$message$segments[[1]]$content, "Starting ")
  expect_equal(captured[[1]]$action$message$segments[[2]]$type, "tool_request")

  # intermediate: chunk for string, block_insert for block
  expect_equal(captured[[2]]$action$type, "chunk")
  expect_equal(captured[[2]]$action$content, " processing ")
  expect_equal(captured[[2]]$action$content_type, "markdown")

  expect_equal(captured[[3]]$action$type, "block_insert")
  expect_equal(captured[[3]]$action$block$type, "tool_result")
  expect_equal(captured[[3]]$action$block$request_id, "req-s1")

  # end: chunk for string, then chunk_end
  expect_equal(captured[[4]]$action$type, "chunk")
  expect_equal(captured[[4]]$action$content, " done")

  expect_equal(captured[[5]]$action$type, "chunk_end")
})

test_that("chat_append_message() block-level html deps are session-processed and on the block", {
  captured <- list()
  local_mocked_bindings(
    send_chat_action = function(id, action, html_deps = NULL, session) {
      captured[[length(captured) + 1]] <<- list(
        action = action,
        html_deps = html_deps
      )
      invisible()
    }
  )
  session <- shiny::MockShinySession$new()

  dep <- htmltools::htmlDependency(
    name = "block-test-dep",
    version = "2.0.0",
    src = ".",
    script = "test.js"
  )

  # Build a tool_result block with a raw htmlDependency stashed on the
  # shinychat_html_deps attribute (as new_tool_card / contents_shinychat do)
  res_block <- structure(
    list(
      type = "tool_result",
      version = 1L,
      request_id = "req-d1",
      tool_name = "compute",
      status = "success",
      value = "42",
      value_type = "markdown"
    ),
    class = c("shinychat_tool_result", "shinychat_block")
  )
  attr(res_block, "shinychat_html_deps") <- list(dep)

  # Non-streaming: the dep is session-processed and attached to the block's
  # html_deps field; it also appears in the envelope-level html_deps
  chat_append_message(
    "chat",
    list(role = "assistant", content = res_block),
    chunk = FALSE,
    session = session
  )

  expect_length(captured, 1)
  msg <- captured[[1]]$action
  expect_equal(msg$type, "message")

  # The block in the segments has html_deps attached
  block_seg <- msg$message$segments[[1]]
  expect_equal(block_seg$type, "tool_result")
  expect_false(is.null(block_seg$html_deps))
  dep_names <- vapply(block_seg$html_deps, function(d) d$name, character(1))
  expect_true("block-test-dep" %in% dep_names)

  # The dep also appears in the envelope-level html_deps
  expect_false(is.null(captured[[1]]$html_deps))
  env_dep_names <- vapply(
    captured[[1]]$html_deps,
    function(d) d$name,
    character(1)
  )
  expect_true("block-test-dep" %in% env_dep_names)

  # The raw attribute is stripped from the block
  expect_null(attr(block_seg, "shinychat_html_deps"))
})

test_that("chat_append_message() emits web_search and web_search_results blocks as segments", {
  captured <- list()
  local_mocked_bindings(
    send_chat_action = function(id, action, html_deps = NULL, session) {
      captured[[length(captured) + 1]] <<- list(
        action = action,
        html_deps = html_deps
      )
      invisible()
    }
  )
  session <- shiny::MockShinySession$new()

  search_block <- new_web_block("web_search", query = "shinychat docs")
  results_block <- new_web_block(
    "web_search_results",
    sources = list(list(url = "https://example.com", title = "Example"))
  )

  # Non-streaming: mixed content with web blocks
  chat_append_message(
    "chat",
    list(
      role = "assistant",
      content = list("Searching... ", search_block, results_block)
    ),
    chunk = FALSE,
    session = session
  )

  expect_length(captured, 1)
  msg <- captured[[1]]$action
  expect_equal(msg$type, "message")
  segments <- msg$message$segments
  expect_length(segments, 3)

  # Segment 1: string -> markdown
  expect_equal(segments[[1]]$content, "Searching... ")
  expect_equal(segments[[1]]$content_type, "markdown")

  # Segment 2: web_search block
  expect_equal(segments[[2]]$type, "web_search")
  expect_equal(segments[[2]]$version, 1L)
  expect_equal(segments[[2]]$query, "shinychat docs")

  # Segment 3: web_search_results block
  expect_equal(segments[[3]]$type, "web_search_results")
  expect_equal(segments[[3]]$version, 1L)
  expect_length(segments[[3]]$sources, 1L)
  expect_equal(segments[[3]]$sources[[1]]$url, "https://example.com")
})

test_that("chat_append_message() emits web_fetch block as segment", {
  captured <- list()
  local_mocked_bindings(
    send_chat_action = function(id, action, html_deps = NULL, session) {
      captured[[length(captured) + 1]] <<- list(
        action = action,
        html_deps = html_deps
      )
      invisible()
    }
  )
  session <- shiny::MockShinySession$new()

  fetch_block <- new_web_block(
    "web_fetch",
    url = "https://example.com",
    status = "success"
  )

  chat_append_message(
    "chat",
    list(role = "assistant", content = fetch_block),
    chunk = FALSE,
    session = session
  )

  expect_length(captured, 1)
  msg <- captured[[1]]$action
  expect_equal(msg$type, "message")
  segments <- msg$message$segments
  expect_length(segments, 1)
  expect_equal(segments[[1]]$type, "web_fetch")
  expect_equal(segments[[1]]$version, 1L)
  expect_equal(segments[[1]]$url, "https://example.com")
  expect_equal(segments[[1]]$status, "success")
})

test_that("chat_append_message() streaming emits block_insert for web blocks", {
  captured <- list()
  local_mocked_bindings(
    send_chat_action = function(id, action, html_deps = NULL, session) {
      captured[[length(captured) + 1]] <<- list(
        action = action,
        html_deps = html_deps
      )
      invisible()
    }
  )
  session <- shiny::MockShinySession$new()

  search_block <- new_web_block("web_search", query = "test")

  # chunk = "end": block emitted as block_insert
  chat_append_message(
    "chat",
    list(role = "assistant", content = list(search_block, " done")),
    chunk = "end",
    session = session
  )

  # First action: block_insert for the web_search block
  expect_equal(captured[[1]]$action$type, "block_insert")
  expect_equal(captured[[1]]$action$block$type, "web_search")
  expect_equal(captured[[1]]$action$block$query, "test")

  # Second action: chunk for the string
  expect_equal(captured[[2]]$action$type, "chunk")
  expect_equal(captured[[2]]$action$content, " done")

  # Third action: chunk_end
  expect_equal(captured[[3]]$action$type, "chunk_end")
})

test_that("chat_server() exposes a failed response until the next succeeds", {
  local_mocked_bindings(
    chat_restore = function(...) invisible(NULL),
    send_chat_action = function(...) invisible(NULL)
  )

  session <- shiny::MockShinySession$new()

  client <- mock_chat_client()
  attempts <- 0
  client$stream_async <- function(...) {
    attempts <<- attempts + 1
    if (attempts == 1) {
      stop("boom")
    }
    "recovered"
  }

  # Driven against a session we keep open, since settling an ExtendedTask and
  # then letting `testServer()` tear its session down leaks an unhandled
  # rejection.
  mod <- shiny::withReactiveDomain(session, {
    chat_server("chat", client, history = FALSE, session = session)
  })

  shiny::withReactiveDomain(session, {
    expect_null(shiny::isolate(mod$last_error()))

    suppressWarnings({
      session$setInputs(chat_user_input = "hi")

      deadline <- Sys.time() + 5
      while (
        is.null(shiny::isolate(mod$last_error())) && Sys.time() < deadline
      ) {
        later::run_now(0.05)
        session$flushReact()
      }
    })

    expect_false(is.null(shiny::isolate(mod$last_error())))
    expect_equal(shiny::isolate(mod$status()), "idle")
    expect_equal(conditionMessage(shiny::isolate(mod$last_error())), "boom")

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

    # Allow the ExtendedTask's finally callback to settle before teardown.
    later::run_now(0.05)
    session$flushReact()

    expect_equal(attempts, 2)
    expect_equal(shiny::isolate(mod$status()), "idle")
    expect_null(shiny::isolate(mod$last_error()))
  })
})
