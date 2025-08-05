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
    req <- new_tool_request()
    expect_null(contents_shinychat(req))
  })
})

test_that("ContentToolRequest rich display", {
  local_shinychat_tool_display(opt = "rich")

  req <- new_tool_request(
    id = "test-123",
    name = "weather",
    arguments = list(.intent = "Check weather", location = "NYC")
  )

  result <- contents_shinychat(req)
  expect_s3_class(result, "shiny.tag")
  expect_equal(result$name, "shiny-tool-request")
  expect_equal(result$attribs$"request-id", "test-123")
  expect_equal(result$attribs$name, "weather")
  expect_equal(result$attribs$intent, "Check weather")
  expect_equal(
    jsonlite::fromJSON(result$attribs$arguments),
    list(.intent = "Check weather", location = "NYC")
  )
})

test_that("ContentToolRequest handles tool annotations", {
  local_shinychat_tool_display(opt = "rich")

  tool <- new_tool(
    name = "weather",
    annotations = list(title = "Weather Tool")
  )
  req <- new_tool_request(tool = tool)
  result <- contents_shinychat(req)
  expect_equal(result$attribs$title, "Weather Tool")
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
  output <- contents_shinychat(result)

  expect_equal(output$attribs$status, "success")
  expect_equal(output$attribs$value, "Success!")
  expect_equal(output$attribs$"value-type", "code")
})

test_that("errors in ContentToolResult are displayed correctly", {
  local_shinychat_tool_display(opt = "rich")

  result <- new_tool_result(error = "Failed!")
  output <- contents_shinychat(result)

  expect_equal(output$attribs$status, "error")
  expect_equal(output$attribs$value, "Failed!")
  expect_equal(output$attribs$"value-type", "code")

  # basic and rich display are the same
  expect_equal(
    with_shinychat_tool_display(opt = "basic", contents_shinychat(result)),
    output
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

  output <- contents_shinychat(result)
  expect_s3_class(output, "shiny.tag")
  expect_equal(output$name, "shiny-tool-result")
  expect_equal(output$attribs$status, "success")
  expect_equal(output$attribs$value, "Success!")
  expect_equal(output$attribs$"value-type", "text")
  expect_equal(output$attribs[["show-request"]], NA)
  expect_null(output$attribs$expanded)
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
  output <- contents_shinychat(result)

  expect_equal(output$attribs$value, "<p>test</p>")
  expect_equal(output$attribs$"value-type", "html")
  expect_null(output$attribs[["show-request"]])
  expect_equal(output$attribs$expanded, NA)
  expect_equal(output$attribs$title, "Custom Title")
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
  output <- contents_shinychat(result)

  expect_equal(format(output$attribs$icon), '<i class="icon"></i>')
  expect_true(list(icon_dep) %in% htmltools::findDependencies(output$children))
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
  output <- contents_shinychat(result)
  expect_equal(
    output$attribs[["request-call"]],
    'test(x = 1, y = "test")'
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
  expect_s3_class(results[[2]], "shiny.tag")
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
    some(messages[[1]]$content, function(x) {
      inherits(x, "shiny.tag") && x$name == "shiny-tool-request"
    })
  )
  expect_true(
    some(messages[[1]]$content, function(x) {
      inherits(x, "shiny.tag") && x$name == "shiny-tool-result"
    })
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
    contents_shinychat(result)
  )
})
