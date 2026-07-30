test_that("opt_shinychat_tool_display handles options and environment variables", {
  withr::local_options(list(shinychat.tool_display = NULL))
  withr::local_envvar(list(SHINYCHAT_TOOL_DISPLAY = NULL))

  # Default behavior
  with_shinychat_tool_display({
    expect_equal(opt_shinychat_tool_display(), "rich")
  })

  # Option setting
  with_shinychat_tool_display(opt = "basic", {
    expect_equal(opt_shinychat_tool_display(), "basic")
  })

  # Environment variable
  with_shinychat_tool_display(envvar = "none", {
    expect_equal(opt_shinychat_tool_display(), "none")
  })

  # Option takes precedence over env var
  with_shinychat_tool_display(envvar = "none", opt = "basic", {
    expect_equal(opt_shinychat_tool_display(), "basic")
  })

  # Invalid values
  with_shinychat_tool_display(envvar = "invalid", {
    expect_snapshot(
      error = TRUE,
      opt_shinychat_tool_display()
    )
  })
  with_shinychat_tool_display(opt = "invalid", {
    expect_snapshot(
      error = TRUE,
      opt_shinychat_tool_display()
    )
  })
})

test_that("basic Content handling works", {
  ContentHTML <- S7::new_class(
    "ContentHTML",
    parent = ellmer::ContentText
  )
  S7::method(contents_shinychat, ContentHTML) <- function(content) {
    shiny::HTML(content@text)
  }

  ContentMarkdown <- S7::new_class(
    "ContentMarkdown",
    parent = ellmer::ContentText
  )
  S7::method(contents_shinychat, ContentMarkdown) <- function(content) {
    content@text
  }

  # Test HTML content
  html_content <- ContentHTML(HTML("<p>test</p>"))
  expect_equal(
    as.character(contents_shinychat(html_content)),
    "<p>test</p>"
  )

  # Test Markdown content
  md_content <- ContentMarkdown("**test**")
  expect_equal(contents_shinychat(md_content), "**test**")

  # Test Text content
  text_content <- ellmer::ContentText("test")
  expect_equal(contents_shinychat(text_content), "test")
})

test_that("ContentToolRequest returns NULL when display is disabled", {
  # Should return NULL when display is none
  with_shinychat_tool_display(opt = "none", {
    request <- new_tool_request()
    expect_null(contents_shinychat(request))
  })
})

test_that("ContentToolRequest rich display", {
  local_shinychat_tool_display(opt = "rich")

  request <- new_tool_request(
    id = "test-123",
    name = "weather",
    arguments = list(`_intent` = "Check weather", location = "NYC")
  )

  res <- contents_shinychat(request)
  expect_s3_class(res, "shinychat_tool_request")
  expect_equal(res$request_id, "test-123")
  expect_equal(res$tool_name, "weather")
  expect_equal(res$intent, "Check weather")
  expect_equal(
    jsonlite::fromJSON(res$arguments),
    list(`_intent` = "Check weather", location = "NYC")
  )

  res_tags <- as.tags(res)
  expect_equal(res_tags$name, "shiny-tool-request")
  expect_equal(res_tags$attribs$"request-id", "test-123")
  expect_equal(res_tags$attribs[["tool-name"]], "weather")
  expect_equal(res_tags$attribs$intent, "Check weather")
  expect_equal(
    jsonlite::fromJSON(res_tags$attribs$arguments),
    list(`_intent` = "Check weather", location = "NYC")
  )
})

test_that("ContentToolRequest handles tool annotations", {
  local_shinychat_tool_display(opt = "rich")

  tool <- new_tool(
    name = "weather",
    annotations = list(title = "Weather Tool")
  )
  request <- new_tool_request(tool = tool)
  res <- contents_shinychat(request)

  expect_s3_class(res, "shinychat_tool_request")
  expect_equal(res$tool_title, "Weather Tool")
})

test_that("ContentToolRequest emits the tool definition icon and its dependencies", {
  # The client compares this static icon against the result's own icon to tell a
  # result-specific icon from the tool's shared identity, so the request has to
  # carry it even though the request card itself doesn't render an icon.
  local_shinychat_tool_display(opt = "rich")

  icon_dep <- htmltools::htmlDependency(
    name = "test",
    version = "1.0",
    src = "."
  )

  tool <- new_tool(
    annotations = list(icon = htmltools::tags$i(class = "icon", icon_dep))
  )
  res <- contents_shinychat(new_tool_request(tool = tool))

  expect_equal(res$icon, tool@annotations$icon)

  res_tags <- as.tags(res)
  expect_equal(format(res_tags$attribs$icon), '<i class="icon"></i>')
  expect_true(
    list(icon_dep) %in% htmltools::findDependencies(res_tags$children)
  )
})

test_that("ContentToolRequest emits no icon when the tool has no icon annotation", {
  local_shinychat_tool_display(opt = "rich")

  res <- contents_shinychat(new_tool_request(tool = new_tool()))

  expect_null(res$icon)
  expect_null(as.tags(res)$attribs$icon)
})

test_that("ContentToolResult requires an associated `@request` property", {
  expect_snapshot(
    error = TRUE,
    contents_shinychat(new_tool_result(request = NULL))
  )
})

test_that("returns NULL for ContentToolResult when display is none", {
  local_shinychat_tool_display(opt = "none")

  base_request <- new_tool_request()
  result <- new_tool_result(request = base_request)

  expect_null(contents_shinychat(result))
})

test_that("simple ContentToolResult are displayed correctly", {
  local_shinychat_tool_display(opt = "rich")

  result <- new_tool_result(value = "Success!")
  res <- contents_shinychat(result)

  expect_s3_class(res, "shinychat_tool_result")
  expect_equal(res$request_id, result@request@id)
  expect_equal(res$tool_name, result@request@name)
  expect_equal(res$value, "Success!")
  expect_equal(res$value_type, "code")
  expect_equal(res$status, "success")
})

test_that("errors in ContentToolResult are displayed correctly", {
  local_shinychat_tool_display(opt = "rich")

  result <- new_tool_result(error = "Failed!")
  res <- contents_shinychat(result)

  expect_s3_class(res, "shinychat_tool_result")
  expect_equal(res$status, "error")
  expect_equal(res$value, "Failed!")
  expect_equal(res$value_type, "code")

  # basic and rich display are the same
  expect_equal(
    with_shinychat_tool_display(opt = "basic", contents_shinychat(result)),
    res
  )
})

test_that("ContentToolResult with custom text display", {
  local_shinychat_tool_display(opt = "rich")

  result <- new_tool_result(
    value = "success",
    extra = list(display = list(text = "Success!"))
  )

  expect_equal(
    tool_result_value(result),
    list(value = "Success!", value_type = "text")
  )

  res <- contents_shinychat(result)
  expect_s3_class(res, "shinychat_tool_result")
  expect_equal(res$request_id, result@request@id)
  expect_equal(res$tool_name, result@request@name)
  expect_equal(res$status, "success")
  expect_equal(res$value, "Success!")
  expect_equal(res$value_type, "text")
  expect_equal(res$show_request, NA)
  expect_null(res$expanded)

  res_tags <- as.tags(res)
  expect_s3_class(res_tags, "shiny.tag")
  expect_equal(res_tags$name, "shiny-tool-result")
  expect_equal(res_tags$attribs$status, "success")
  expect_equal(res_tags$attribs$value, "Success!")
  expect_equal(res_tags$attribs$"value-type", "text")
  expect_equal(res_tags$attribs[["show-request"]], NA)
  expect_null(res_tags$attribs$expanded)
})

test_that("ContentToolResult with additional display options from result", {
  local_shinychat_tool_display(opt = "rich")

  result <- new_tool_result(
    value = "test",
    extra = list(
      display = list(
        html = "<p>test</p>",
        show_request = FALSE,
        open = TRUE,
        title = "Custom Title"
      )
    )
  )
  res <- contents_shinychat(result)
  expect_s3_class(res, "shinychat_tool_result")
  expect_equal(res$value, "<p>test</p>")
  expect_equal(res$value_type, "html")
  expect_equal(res$show_request, NULL)
  expect_equal(res$expanded, NA)
  expect_equal(res$tool_title, "Custom Title")

  res_tags <- as.tags(res)
  expect_equal(res_tags$attribs$value, "<p>test</p>")
  expect_equal(res_tags$attribs$"value-type", "html")
  expect_equal(res_tags$attribs[["show-request"]], NULL)
  expect_equal(res_tags$attribs$expanded, NA)
  expect_equal(res_tags$attribs[["tool-title"]], "Custom Title")
})

test_that("ContentToolResult with HTML() title preserves markup", {
  local_shinychat_tool_display(opt = "rich")

  result <- new_tool_result(
    value = "test",
    extra = list(
      display = list(
        text = "test",
        title = HTML("Map of <i>Paris</i>")
      )
    )
  )
  res <- contents_shinychat(result)
  expect_s3_class(res$tool_title, "html")
  expect_equal(as.character(res$tool_title), "Map of <i>Paris</i>")

  # htmltools always escapes attribute values, but the browser decodes them,
  # so JS getAttribute() returns the original HTML string. The Playwright

  # test (test_html_title.py) verifies the end-to-end rendering.
  res_tags <- as.tags(res)
  expect_equal(res_tags$attribs[["tool-title"]], HTML("Map of <i>Paris</i>"))
})

test_that("ContentToolResult handles icon and dependencies from tool definition", {
  local_shinychat_tool_display(opt = "rich")

  icon_dep <- htmltools::htmlDependency(
    name = "test",
    version = "1.0",
    src = "."
  )

  tool <- new_tool(
    annotations = list(
      icon = htmltools::tags$i(class = "icon", icon_dep)
    )
  )
  result <- new_tool_result(
    value = "test",
    request = new_tool_request(tool = tool),
    extra = list(display = list(text = "test"))
  )

  res <- contents_shinychat(result)
  expect_s3_class(res, "shinychat_tool_result")
  expect_equal(res$icon, tool@annotations$icon)

  res_tags <- as.tags(res)
  expect_equal(format(res_tags$attribs$icon), '<i class="icon"></i>')
  expect_true(
    list(icon_dep) %in% htmltools::findDependencies(res_tags$children)
  )
})

test_that("ContentToolResult formats request_call correctly", {
  local_shinychat_tool_display(opt = "rich")

  result <- new_tool_result(
    value = "test",
    request = new_tool_request(
      name = "test",
      arguments = list(x = 1, y = "test")
    )
  )
  res <- contents_shinychat(result)
  expect_equal(res$request_call, 'test(x = 1, y = "test")')

  result@request@tool <- NULL
  res_no_tool <- contents_shinychat(result)
  expect_equal(
    jsonlite::fromJSON(res_no_tool$request_call),
    list(
      id = result@request@id,
      name = result@request@name,
      arguments = result@request@arguments
    )
  )
})

test_that("get_tool_result_display handles invalid formats", {
  # Test direct HTML warning
  result <- new_tool_result(
    extra = list(display = htmltools::tags$p("test"))
  )

  expect_snapshot(
    get_tool_result_display(result)
  )

  # Test non-list warning
  result <- new_tool_result(
    extra = list(display = "invalid")
  )
  expect_snapshot(
    get_tool_result_display(result)
  )
})

test_that("tool_result_display basic format", {
  local_shinychat_tool_display(opt = "basic")
  result <- new_tool_result(
    value = list(x = 1),
    extra = list(display = list(text = "ignored in basic mode"))
  )
  expect_equal(
    tool_result_value(result),
    list(
      value = jsonlite::toJSON(list(x = 1), auto_unbox = TRUE, pretty = 2),
      value_type = "code"
    )
  )
})

test_that("tool_result_display rich format", {
  local_shinychat_tool_display(opt = "rich")
  result <- new_tool_result(
    value = "test",
    extra = list(
      display = list(
        html = "<p>html</p>",
        markdown = "**md**",
        text = "text"
      )
    )
  )
  expect_equal(
    tool_result_value(result),
    list(value = "<p>html</p>", value_type = "html")
  )
})

test_that("processes a Turn object", {
  # Create a turn with multiple content items
  turn <- ellmer::AssistantTurn(
    contents = list(
      ellmer::ContentText("Hello"),
      new_tool_request(),
      ellmer::ContentText("World")
    )
  )

  # Process turn contents
  results <- contents_shinychat(turn)
  expect_length(results, 3)
  expect_equal(results[[1]], "Hello")
  expect_s3_class(results[[2]], "shinychat_tool_request")
  expect_equal(results[[3]], "World")
})

test_that("consolidates adjacent turn types in a Chat object", {
  withr::local_options(OPENAI_API_KEY = "boop")
  chat <- ellmer::chat_openai()

  chat$set_turns(
    list(
      ellmer::AssistantTurn(
        contents = list(ellmer::ContentText("Hello"))
      ),
      ellmer::AssistantTurn(
        contents = list(ellmer::ContentText("World"))
      )
    )
  )

  messages <- contents_shinychat(chat)
  expect_length(messages, 1)
  expect_equal(messages[[1]]$role, "assistant")
  expect_equal(messages[[1]]$content, "Hello\n\nWorld")
})

test_that("doesn't consolidate adjacent turns with different roles in a Chat object", {
  withr::local_options(OPENAI_API_KEY = "boop")
  chat <- ellmer::chat_openai()

  chat$set_turns(
    list(
      ellmer::UserTurn(
        contents = list(ellmer::ContentText("Question"))
      ),
      ellmer::AssistantTurn(
        contents = list(ellmer::ContentText("Answer"))
      )
    )
  )

  messages <- contents_shinychat(chat)
  expect_length(messages, 2) # Previous consolidated message + 2 new messages
  expect_equal(messages[[1]]$role, "user")
  expect_equal(messages[[2]]$role, "assistant")
})

test_that("keeps requests with results in a consolidated assistant turn in a Chat object", {
  withr::local_options(OPENAI_API_KEY = "boop")
  chat <- ellmer::chat_openai()

  chat$set_turns(
    list(
      ellmer::AssistantTurn(
        contents = list(
          ellmer::ContentText("Hello"),
          new_tool_request()
        )
      ),
      ellmer::UserTurn(
        contents = list(
          new_tool_result(value = "success")
        )
      )
    )
  )

  messages <- contents_shinychat(chat)
  expect_length(messages, 1)
  expect_equal(messages[[1]]$role, "assistant")

  # The request is kept (not filtered) and consolidated into the same message
  # as its result, so the client pairs them by request-id and the result
  # inherits the request's arguments.
  expect_true(
    some(messages[[1]]$content, inherits, "shinychat_tool_request")
  )
  expect_true(
    some(messages[[1]]$content, inherits, "shinychat_tool_result")
  )
})

test_that("throws when a result does not have a `request` property", {
  expect_snapshot(
    error = TRUE,
    contents_shinychat(new_tool_result(request = NULL))
  )
})

test_that("throws for invalid tool display option", {
  withr::local_options(shinychat.tool_display = "invalid")
  expect_snapshot(
    error = TRUE,
    opt_shinychat_tool_display()
  )
})

test_that("throws for invalid tool display ennvar", {
  withr::local_envvar(SHINYCHAT_TOOL_DISPLAY = "invalid")
  expect_snapshot(
    error = TRUE,
    opt_shinychat_tool_display()
  )
})

test_that("warns when `display` is not a list", {
  result <- new_tool_result(
    request = new_tool_request(),
    extra = list(display = htmltools::tags$p("test"))
  )
  expect_snapshot(
    as.tags(contents_shinychat(result))
  )
})

test_that("tool_result_display() round-trips its fields", {
  display <- tool_result_display(
    title = "Title",
    icon = "icon",
    html = "<p>html</p>",
    markdown = "**md**",
    text = "text",
    show_request = FALSE,
    open = TRUE,
    full_screen = TRUE,
    footer = "Footer",
    label = "Label",
    value_preview = "Preview"
  )

  expect_s3_class(display, "shinychat_tool_result_display")
  expect_equal(display$title, "Title")
  expect_equal(display$icon, "icon")
  expect_equal(display$html, "<p>html</p>")
  expect_equal(display$markdown, "**md**")
  expect_equal(display$text, "text")
  expect_equal(display$show_request, FALSE)
  expect_equal(display$open, TRUE)
  expect_equal(display$full_screen, TRUE)
  expect_equal(display$footer, "Footer")
  expect_equal(display$label, "Label")
  expect_equal(display$value_preview, "Preview")
})

test_that("tool_result_display() drops NULL fields but keeps defaults", {
  display <- tool_result_display(title = "Title only")

  expect_s3_class(display, "shinychat_tool_result_display")
  expect_equal(
    display,
    structure(
      list(
        title = "Title only",
        show_request = TRUE,
        open = FALSE,
        full_screen = FALSE
      ),
      class = "shinychat_tool_result_display"
    )
  )
})

test_that("as_tool_result_display() promotes a bare list", {
  res <- as_tool_result_display(list(title = "Bare list"))
  expect_s3_class(res, "shinychat_tool_result_display")
  expect_equal(res$title, "Bare list")
})

test_that("as_tool_result_display() passes an existing S3 object through unchanged", {
  display <- tool_result_display(title = "Already an object")
  expect_identical(as_tool_result_display(display), display)
})

test_that("as_tool_result_display() warns and drops unrecognized fields", {
  expect_warning(
    res <- as_tool_result_display(list(title = "Known", bogus = "nope")),
    class = "rlang_warning"
  )
  expect_s3_class(res, "shinychat_tool_result_display")
  expect_equal(res$title, "Known")
  expect_null(res$bogus)
})

test_that("as_tool_result_display() warns and drops non-logical flag fields", {
  expect_warning(
    res <- as_tool_result_display(
      list(show_request = "false", open = 1, full_screen = "yes")
    ),
    class = "rlang_warning"
  )
  expect_null(res$show_request)
  expect_null(res$open)
  expect_null(res$full_screen)
})

test_that("as_tool_result_display() rejects non-scalar and NA logicals", {
  expect_warning(
    res <- as_tool_result_display(list(open = c(TRUE, TRUE))),
    class = "rlang_warning"
  )
  expect_null(res$open)

  # `NA` is a logical scalar but not a usable value: `isTRUE(NA)` and
  # `isFALSE(NA)` are both `FALSE`, so it's dropped like any other bad value.
  expect_warning(
    res <- as_tool_result_display(list(show_request = NA)),
    class = "rlang_warning"
  )
  expect_null(res$show_request)
})

test_that("as_tool_result_display() keeps valid logical flags", {
  res <- as_tool_result_display(
    list(show_request = FALSE, open = TRUE, full_screen = TRUE)
  )
  expect_equal(res$show_request, FALSE)
  expect_equal(res$open, TRUE)
  expect_equal(res$full_screen, TRUE)
})

test_that("as_tool_result_display() validates text and HTML fields", {
  expect_warning(
    res <- as_tool_result_display(
      list(label = 1, value_preview = NA_character_, text = c("a", "b"))
    ),
    class = "rlang_warning"
  )
  expect_null(res$label)
  expect_null(res$value_preview)
  expect_null(res$text)

  # HTML-rendered fields accept strings or tag-like content
  res <- as_tool_result_display(
    list(
      title = HTML("Map of <i>Paris</i>"),
      icon = htmltools::tags$i(class = "icon"),
      footer = "Footer",
      html = htmltools::tags$p("html")
    )
  )
  expect_equal(res$title, HTML("Map of <i>Paris</i>"))
  expect_equal(res$icon, htmltools::tags$i(class = "icon"))
  expect_equal(res$footer, "Footer")
  expect_equal(res$html, htmltools::tags$p("html"))

  expect_warning(
    res <- as_tool_result_display(list(title = 1)),
    class = "rlang_warning"
  )
  expect_null(res$title)
})

test_that("tool_result_display() validates its arguments", {
  expect_warning(
    display <- tool_result_display(title = "Title", open = 1),
    class = "rlang_warning"
  )
  expect_s3_class(display, "shinychat_tool_result_display")
  expect_equal(display$title, "Title")
  expect_null(display$open)
})

test_that("malformed display flags serialize to their defaults", {
  local_shinychat_tool_display(opt = "rich")

  result <- new_tool_result(
    value = "test",
    extra = list(
      display = list(
        text = "test",
        show_request = "false",
        open = 1,
        full_screen = "yes"
      )
    )
  )

  expect_warning(res <- contents_shinychat(result), class = "rlang_warning")

  # Defaults: the request is shown, the card is collapsed and not full screen
  expect_equal(res$show_request, NA)
  expect_null(res$expanded)
  expect_null(res$full_screen)

  # A well-formed bare list is still honored end to end
  result_ok <- new_tool_result(
    value = "test",
    extra = list(
      display = list(
        text = "test",
        show_request = FALSE,
        open = TRUE,
        full_screen = TRUE
      )
    )
  )
  res_ok <- contents_shinychat(result_ok)
  expect_null(res_ok$show_request)
  expect_equal(res_ok$expanded, NA)
  expect_equal(res_ok$full_screen, NA)
})

test_that("as_tool_result_display() warns and returns an empty object for non-list input", {
  expect_warning(
    res <- as_tool_result_display("not a list"),
    class = "rlang_warning"
  )
  expect_equal(
    res,
    structure(list(), class = "shinychat_tool_result_display")
  )
})

test_that("S3 display object and equivalent bare list serialize identically", {
  local_shinychat_tool_display(opt = "rich")

  display_args <- list(
    title = "Custom Title",
    text = "Custom text",
    label = "call-1",
    value_preview = "preview text",
    show_request = FALSE,
    open = TRUE
  )

  result_s3 <- new_tool_result(
    value = "test",
    extra = list(display = rlang::exec(tool_result_display, !!!display_args))
  )
  result_list <- new_tool_result(
    value = "test",
    extra = list(display = display_args)
  )

  res_s3 <- contents_shinychat(result_s3)
  res_list <- contents_shinychat(result_list)

  # request_id differs only because each `new_tool_result()` call generates a
  # fresh request; strip it before comparing.
  res_s3$request_id <- NULL
  res_list$request_id <- NULL
  expect_equal(res_s3, res_list)

  tags_s3 <- as.tags(contents_shinychat(result_s3))
  tags_list <- as.tags(contents_shinychat(result_list))
  tags_s3$attribs$"request-id" <- NULL
  tags_list$attribs$"request-id" <- NULL
  expect_equal(format(tags_s3), format(tags_list))
})

test_that("tool_result_value() selects markdown when only markdown is provided", {
  local_shinychat_tool_display(opt = "rich")

  result <- new_tool_result(
    value = "test",
    extra = list(display = list(markdown = "**bold**"))
  )
  expect_equal(
    tool_result_value(result),
    list(value = "**bold**", value_type = "markdown")
  )
})

test_that("as_grouping() validates tool annotation values", {
  expect_equal(as_grouping("none"), "none")
  expect_equal(as_grouping("tool"), "tool")
  expect_equal(as_grouping("all"), "all")

  expect_null(as_grouping(NULL))
  expect_null(as_grouping(c("tool", "all")))
  expect_null(as_grouping(1))
  expect_null(as_grouping("invalid"))
})

test_that("ContentToolRequest emits grouping from tool annotations", {
  local_shinychat_tool_display(opt = "rich")

  tool <- new_tool(annotations = list(grouping = "all"))
  request <- new_tool_request(tool = tool)
  res <- contents_shinychat(request)

  expect_equal(res$grouping, "all")

  res_tags <- as.tags(res)
  expect_equal(res_tags$attribs$grouping, "all")
})

test_that("ContentToolResult emits grouping from tool annotations", {
  local_shinychat_tool_display(opt = "rich")

  tool <- new_tool(annotations = list(grouping = "all"))
  result <- new_tool_result(
    value = "test",
    request = new_tool_request(tool = tool)
  )
  res <- contents_shinychat(result)

  expect_equal(res$grouping, "all")

  res_tags <- as.tags(res)
  expect_equal(res_tags$attribs$grouping, "all")
})

test_that("invalid tool annotation grouping is dropped (no attribute emitted)", {
  local_shinychat_tool_display(opt = "rich")

  tool <- new_tool(annotations = list(grouping = "bogus"))
  result <- new_tool_result(
    value = "test",
    request = new_tool_request(tool = tool)
  )
  res <- contents_shinychat(result)

  expect_null(res$grouping)
  res_tags <- as.tags(res)
  expect_null(res_tags$attribs$grouping)
})

test_that("basic tool display suppresses custom display metadata but keeps annotations", {
  tool <- new_tool(annotations = list(grouping = "all", title = "Weather Tool"))
  request <- new_tool_request(tool = tool)
  result <- new_tool_result(
    value = "ok",
    request = request,
    extra = list(
      display = list(
        text = "ignored in basic mode",
        label = "ignored label",
        value_preview = "ignored preview"
      )
    )
  )

  local_shinychat_tool_display(opt = "basic")

  req_res <- contents_shinychat(request)
  expect_s3_class(req_res, "shinychat_tool_request")
  expect_equal(req_res$tool_title, "Weather Tool")
  expect_equal(req_res$grouping, "all")

  tool_res <- contents_shinychat(result)
  expect_s3_class(tool_res, "shinychat_tool_result")
  expect_equal(tool_res$tool_title, "Weather Tool")
  expect_equal(tool_res$grouping, "all")
  expect_null(tool_res$label)
  expect_null(tool_res$value_preview)
  # Falls back to the actual value, not the (suppressed) custom display text
  expect_equal(tool_res$value, "ok")
  expect_equal(tool_res$value_type, "code")
})

test_that("no tool elements are rendered when display is disabled entirely", {
  tool <- new_tool(annotations = list(grouping = "all", title = "Weather Tool"))
  request <- new_tool_request(tool = tool)
  result <- new_tool_result(value = "ok", request = request)

  local_shinychat_tool_display(opt = "none")

  expect_null(contents_shinychat(request))
  expect_null(contents_shinychat(result))
})

test_that("ellmer_turn_effective_role() treats a tool-result-only turn as assistant", {
  plain_user <- ellmer::UserTurn(contents = list(ellmer::ContentText("hi")))
  plain_assistant <- ellmer::AssistantTurn(
    contents = list(ellmer::ContentText("hi"))
  )
  tool_result_turn <- ellmer::UserTurn(
    contents = list(new_tool_result(value = "ok"))
  )

  expect_equal(ellmer_turn_effective_role(plain_user), "user")
  expect_equal(ellmer_turn_effective_role(plain_assistant), "assistant")
  expect_equal(ellmer_turn_effective_role(tool_result_turn), "assistant")
})

test_that("group_ellmer_turns() keeps a plain user/assistant exchange as two groups", {
  turns <- list(
    ellmer::UserTurn(contents = list(ellmer::ContentText("hi"))),
    ellmer::AssistantTurn(contents = list(ellmer::ContentText("hello")))
  )
  groups <- group_ellmer_turns(turns)
  expect_length(groups, 2)
  expect_equal(groups[[1]], list(turns[[1]]))
  expect_equal(groups[[2]], list(turns[[2]]))
})

test_that("group_ellmer_turns() consolidates a tool-call round into one group", {
  request <- new_tool_request(id = "t1", name = "get_weather")
  turns <- list(
    ellmer::UserTurn(
      contents = list(ellmer::ContentText("what's the weather?"))
    ),
    ellmer::AssistantTurn(
      contents = list(ellmer::ContentText("Let me check."), request)
    ),
    ellmer::UserTurn(
      contents = list(new_tool_result(value = "Sunny, 75F", request = request))
    ),
    ellmer::AssistantTurn(
      contents = list(ellmer::ContentText("It's sunny and 75F!"))
    )
  )
  groups <- group_ellmer_turns(turns)
  expect_length(groups, 2)
  expect_equal(groups[[1]], list(turns[[1]]))
  expect_equal(groups[[2]], turns[2:4])
})

test_that("group_ellmer_turns() merges adjacent same-role turns with no tool call", {
  turns <- list(
    ellmer::AssistantTurn(contents = list(ellmer::ContentText("Hello"))),
    ellmer::AssistantTurn(contents = list(ellmer::ContentText("World")))
  )
  groups <- group_ellmer_turns(turns)
  expect_length(groups, 1)
  expect_equal(groups[[1]], turns)
})

test_that("group_ellmer_turns() returns an empty list for no turns", {
  expect_equal(group_ellmer_turns(list()), list())
})
