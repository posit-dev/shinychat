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
    tool_result_display(result),
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
  expect_equal(res_tags$attribs$value, html_escape("<p>test</p>"))
  expect_equal(res_tags$attribs$"value-type", "html")
  expect_equal(res_tags$attribs[["show-request"]], NULL)
  expect_equal(res_tags$attribs$expanded, NA)
  expect_equal(res_tags$attribs[["tool-title"]], "Custom Title")
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
  expect_equal(
    format(res_tags$attribs$icon),
    html_escape('<i class="icon"></i>')
  )
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
    tool_result_display(result),
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
    tool_result_display(result),
    list(value = "<p>html</p>", value_type = "html")
  )
})

test_that("processes a Turn object", {
  # Create a turn with multiple content items
  turn <- ellmer::Turn(
    role = "assistant",
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
  chat <- ellmer::chat_openai(api_key = "boop")

  chat$set_turns(list(
    ellmer::Turn(
      role = "assistant",
      contents = list(ellmer::ContentText("Hello"))
    ),
    ellmer::Turn(
      role = "assistant",
      contents = list(ellmer::ContentText("World"))
    )
  ))

  messages <- contents_shinychat(chat)
  expect_length(messages, 1)
  expect_equal(messages[[1]]$role, "assistant")
  expect_equal(messages[[1]]$content, "Hello\n\nWorld")
})

test_that("doesn't consolidate adjacent turns with different roles in a Chat object", {
  chat <- ellmer::chat_openai(api_key = "boop")

  chat$set_turns(list(
    ellmer::Turn(
      role = "user",
      contents = list(ellmer::ContentText("Question"))
    ),
    ellmer::Turn(
      role = "assistant",
      contents = list(ellmer::ContentText("Answer"))
    )
  ))

  messages <- contents_shinychat(chat)
  expect_length(messages, 2) # Previous consolidated message + 2 new messages
  expect_equal(messages[[1]]$role, "user")
  expect_equal(messages[[2]]$role, "assistant")
})

test_that("drops requests and moves results to assistant turn role in a Chat object", {
  chat <- ellmer::chat_openai(api_key = "boop")

  chat$set_turns(list(
    ellmer::Turn(
      role = "assistant",
      contents = list(
        ellmer::ContentText("Hello"),
        new_tool_request()
      )
    ),
    ellmer::Turn(
      role = "user",
      contents = list(
        new_tool_result(value = "success")
      )
    )
  ))

  messages <- contents_shinychat(chat)
  expect_length(messages, 1)
  expect_equal(messages[[1]]$role, "assistant")

  # Verify tool requests are filtered but results appear
  expect_false(
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
