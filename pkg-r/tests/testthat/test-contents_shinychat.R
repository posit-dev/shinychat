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
  expect_s3_class(res, "shinychat_block")
  expect_equal(res$type, "tool_request")
  expect_equal(res$version, 1L)
  expect_equal(res$request_id, "test-123")
  expect_equal(res$tool_name, "weather")
  expect_equal(res$intent, "Check weather")
  expect_equal(
    jsonlite::fromJSON(res$arguments),
    list(`_intent` = "Check weather", location = "NYC")
  )
})

test_that("tool card serialization matches the shared wire fixture", {
  fixture <- jsonlite::read_json(
    test_path("fixtures", "tool-wire-protocol.json"),
    simplifyVector = TRUE
  )

  request <- new_tool_card(
    "tool_request",
    request_id = "wire-1",
    tool_name = "search",
    title = "Searching",
    icon = "<i>search</i>",
    intent = "Find docs",
    arguments = '{"q":"shiny"}',
    grouping = "all"
  )
  result <- new_tool_card(
    "tool_result",
    request_id = "wire-1",
    tool_name = "search",
    title = "Searched",
    icon = "<i>done</i>",
    intent = "Find docs",
    status = "success",
    label = "docs",
    value_preview = "3 results",
    value = "Result body",
    value_type = "markdown",
    request_call = 'search(q="shiny")',
    show_request = TRUE,
    full_screen = TRUE,
    expanded = TRUE,
    footer = "<span>footer</span>",
    grouping = "all",
    open_style = "framed"
  )

  req_expected <- fixture$blocks$request
  expect_equal(request$type, req_expected$type)
  expect_equal(request$version, req_expected$version)
  expect_equal(request$request_id, req_expected$request_id)
  expect_equal(request$tool_name, req_expected$tool_name)
  expect_equal(request$title, req_expected$title)
  expect_equal(request$icon, req_expected$icon)
  expect_equal(request$intent, req_expected$intent)
  expect_equal(request$arguments, req_expected$arguments)
  expect_equal(request$grouping, req_expected$grouping)

  res_expected <- fixture$blocks$result
  expect_equal(result$type, res_expected$type)
  expect_equal(result$version, res_expected$version)
  expect_equal(result$request_id, res_expected$request_id)
  expect_equal(result$tool_name, res_expected$tool_name)
  expect_equal(result$title, res_expected$title)
  expect_equal(result$icon, res_expected$icon)
  expect_equal(result$intent, res_expected$intent)
  expect_equal(result$status, res_expected$status)
  expect_equal(result$label, res_expected$label)
  expect_equal(result$value_preview, res_expected$value_preview)
  expect_equal(result$value, res_expected$value)
  expect_equal(result$value_type, res_expected$value_type)
  expect_equal(result$request_call, res_expected$request_call)
  expect_equal(result$show_request, res_expected$show_request)
  expect_equal(result$full_screen, res_expected$full_screen)
  expect_equal(result$expanded, res_expected$expanded)
  expect_equal(result$open_style, res_expected$open_style)
  expect_equal(result$footer, res_expected$footer)
  expect_equal(result$grouping, res_expected$grouping)
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
  expect_equal(res$title, "Weather Tool")
})

test_that("absent annotation title yields no title field, not character(0)", {
  local_shinychat_tool_display(opt = "rich")

  request <- new_tool_request(tool = new_tool(name = "weather"))
  res <- contents_shinychat(request)
  expect_true(is.null(res$title))

  result <- new_tool_result(value = "ok", request = request)
  res <- contents_shinychat(result)
  expect_true(is.null(res$title))
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

  expect_equal(res$icon, '<i class="icon"></i>')
  block_deps <- attr(res, "shinychat_html_deps")
  expect_true("test" %in% vapply(block_deps, function(d) d$name, character(1)))
})

test_that("ContentToolRequest emits no icon when the tool has no icon annotation", {
  local_shinychat_tool_display(opt = "rich")

  res <- contents_shinychat(new_tool_request(tool = new_tool()))

  expect_null(res$icon)
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
  expect_s3_class(res, "shinychat_block")
  expect_equal(res$type, "tool_result")
  expect_equal(res$version, 1L)
  expect_equal(res$request_id, result@request@id)
  expect_equal(res$tool_name, result@request@name)
  expect_equal(res$status, "success")
  expect_equal(res$value, "Success!")
  expect_equal(res$value_type, "text")
  expect_true(res$show_request)
  expect_false(res$expanded)
  expect_false(res$full_screen)
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
  expect_false(res$show_request)
  expect_true(res$expanded)
  expect_equal(res$title, "Custom Title")
})

test_that("ContentToolResult serializes framed open style only when requested", {
  local_shinychat_tool_display(opt = "rich")

  framed <- new_tool_result(
    value = "test",
    extra = list(display = tool_result_display(open_style = "framed"))
  )
  minimal <- new_tool_result(
    value = "test",
    extra = list(display = tool_result_display())
  )

  expect_equal(contents_shinychat(framed)$open_style, "framed")
  expect_null(contents_shinychat(minimal)$open_style)
})

test_that("mutating a card's title overrides the annotation title", {
  # The documented pattern for a custom result class (see the
  # `contents_shinychat()` example): call the super method, then mutate the
  local_shinychat_tool_display(opt = "rich")

  result <- new_tool_result(
    value = "test",
    request = new_tool_request(
      tool = new_tool(annotations = ellmer::tool_annotations(title = "Static"))
    )
  )
  res <- contents_shinychat(result)
  expect_equal(res$title, "Static")

  res$title <- "Dynamic for Portland"
  expect_equal(res$title, "Dynamic for Portland")
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
  expect_equal(res$title, "Map of <i>Paris</i>")
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
  expect_equal(res$icon, '<i class="icon"></i>')
  block_deps <- attr(res, "shinychat_html_deps")
  expect_true("test" %in% vapply(block_deps, function(d) d$name, character(1)))
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

test_that("web content emitters produce structured shinychat_block lists", {
  local_shinychat_tool_display(opt = "rich")


  MockSearchRequest <- S7::new_class(
    "MockSearchRequest",
    properties = list(query = S7::class_character)
  )
  MockSearchResponse <- S7::new_class(
    "MockSearchResponse",
    properties = list(sources = S7::class_list)
  )
  MockWebSource <- S7::new_class(
    "MockWebSource",
    properties = list(url = S7::class_character, title = S7::class_character)
  )
  MockFetchResponse <- S7::new_class(
    "MockFetchResponse",
    properties = list(url = S7::class_character, status = S7::class_character)
  )

  search_content <- MockSearchRequest(query = "ggplot2 release date")
  search_block <- contents_shinychat_search_request(search_content)
  expect_s3_class(search_block, "shinychat_web_search")
  expect_s3_class(search_block, "shinychat_block")
  expect_equal(search_block$type, "web_search")
  expect_equal(search_block$version, 1L)
  expect_equal(search_block$query, "ggplot2 release date")

  results_content <- MockSearchResponse(
    sources = list(
      MockWebSource(
        url = "https://cran.r-project.org/package=ggplot2",
        title = "ggplot2"
      ),
      MockWebSource(url = "https://example.com", title = NA_character_),
      MockWebSource(url = NA_character_, title = "No URL")
    )
  )
  results_block <- contents_shinychat_search_response(results_content)
  expect_s3_class(results_block, "shinychat_web_search_results")
  expect_s3_class(results_block, "shinychat_block")
  expect_equal(results_block$type, "web_search_results")
  expect_equal(results_block$version, 1L)
  expect_length(results_block$sources, 2L)
  expect_equal(
    results_block$sources[[1]]$url,
    "https://cran.r-project.org/package=ggplot2"
  )
  expect_equal(results_block$sources[[1]]$title, "ggplot2")
  expect_equal(results_block$sources[[2]]$url, "https://example.com")
  expect_false("title" %in% names(results_block$sources[[2]]))

  expect_null(contents_shinychat_fetch_request(list()))

  fetch_content <- MockFetchResponse(
    url = "https://example.com",
    status = "success"
  )
  fetch_block <- contents_shinychat_fetch_response(fetch_content)
  expect_s3_class(fetch_block, "shinychat_web_fetch")
  expect_s3_class(fetch_block, "shinychat_block")
  expect_equal(fetch_block$type, "web_fetch")
  expect_equal(fetch_block$version, 1L)
  expect_equal(fetch_block$url, "https://example.com")
  expect_equal(fetch_block$status, "success")

  fetch_error <- MockFetchResponse(
    url = "https://example.com",
    status = "error"
  )
  expect_null(contents_shinychat_fetch_response(fetch_error))

  fetch_no_url <- MockFetchResponse(url = NA_character_, status = "success")
  expect_null(contents_shinychat_fetch_response(fetch_no_url))
})

test_that("web content emitters respect disabled tool display", {
  local_shinychat_tool_display(opt = "none")

  MockSearchRequest <- S7::new_class(
    "MockSearchRequest2",
    properties = list(query = S7::class_character)
  )
  MockSearchResponse <- S7::new_class(
    "MockSearchResponse2",
    properties = list(sources = S7::class_list)
  )
  MockFetchResponse <- S7::new_class(
    "MockFetchResponse2",
    properties = list(url = S7::class_character, status = S7::class_character)
  )

  search_content <- MockSearchRequest(query = "test")
  expect_null(contents_shinychat_search_request(search_content))

  results_content <- MockSearchResponse(sources = list())
  expect_null(contents_shinychat_search_response(results_content))

  fetch_content <- MockFetchResponse(
    url = "https://example.com",
    status = "success"
  )
  expect_null(contents_shinychat_fetch_response(fetch_content))
})

test_that("web_source_record omits title when NA and filters NA urls", {
  MockWebSource <- S7::new_class(
    "MockWebSource2",
    properties = list(url = S7::class_character, title = S7::class_character)
  )

  source_with_title <- MockWebSource(
    url = "https://example.com",
    title = "Example"
  )
  record <- web_source_record(source_with_title)
  expect_equal(record, list(url = "https://example.com", title = "Example"))

  source_no_title <- MockWebSource(
    url = "https://example.com",
    title = NA_character_
  )
  record <- web_source_record(source_no_title)
  expect_equal(record, list(url = "https://example.com"))
  expect_false("title" %in% names(record))

  source_no_url <- MockWebSource(url = NA_character_, title = "No URL")
  expect_null(web_source_record(source_no_url))
})

test_that("ContentCitation preserves optional metadata independently", {
  skip_if_not(ellmer_web_content_available(ellmer_web_content_methods()))

  grounded_only <- contents_shinychat(
    ellmer::ContentCitation(
      source = ellmer::WebSource("https://x.example", "Example"),
      grounded_span = "Supported answer"
    )
  )
  expect_match(
    grounded_only,
    'grounded-span="Supported answer"',
    fixed = TRUE
  )
  expect_false(grepl("cited-quote=", grounded_only, fixed = TRUE))

  quote_only <- contents_shinychat(
    ellmer::ContentCitation(
      source = ellmer::WebSource("https://x.example", "Example"),
      cited_quote = "Source evidence"
    )
  )
  expect_match(quote_only, 'cited-quote="Source evidence"', fixed = TRUE)
  expect_false(grepl("grounded-span=", quote_only, fixed = TRUE))
})

test_that("web content feature detection derives classes from registered methods", {
  methods <- ellmer_web_content_methods()
  exports <- c("WebSource", names(methods))

  expect_true(ellmer_web_content_available(methods, exports))
  expect_false(ellmer_web_content_available(methods, exports[-1]))
  expect_false(ellmer_web_content_available(methods, exports[-2]))
})

test_that("attach_cited_sources adds cited_sources to last web_search when no results", {
  search_block <- new_web_block("web_search", query = "test query")
  content <- list("answer text", search_block)

  result <- attach_cited_sources(list(), content)
  expect_null(result[[2]]$cited_sources)

  results_block <- new_web_block(
    "web_search_results",
    sources = list(list(url = "https://provider.example", title = "Provider"))
  )
  content_with_results <- list("answer", search_block, results_block)
  result <- attach_cited_sources(list(), content_with_results)
  expect_null(result[[2]]$cited_sources)

  content_no_search <- list("just text")
  result <- attach_cited_sources(list(), content_no_search)
  expect_equal(result, content_no_search)
})

test_that("attach_cited_sources backfills a missing title from a later citation for the same URL", {
  skip_if_not(ellmer_web_content_available(ellmer_web_content_methods()))

  cit_no_title <- ellmer::ContentCitation(
    source = ellmer::WebSource("https://shared.example", title = NULL),
    grounded_span = "claim one"
  )
  cit_with_title <- ellmer::ContentCitation(
    source = ellmer::WebSource("https://shared.example", "Later Title"),
    grounded_span = "claim two"
  )
  raw_contents <- list(cit_no_title, cit_with_title)

  search_block <- new_web_block("web_search", query = "test")
  content <- list("answer", search_block)

  result <- attach_cited_sources(raw_contents, content)
  expect_false(is.null(result[[2]]$cited_sources))
  expect_length(result[[2]]$cited_sources, 1L)
  expect_equal(result[[2]]$cited_sources[[1]]$url, "https://shared.example")
  expect_equal(result[[2]]$cited_sources[[1]]$title, "Later Title")
})

test_that("Turn conversion attaches cited_sources to a results-less web_search", {
  skip_if_not(ellmer_web_content_available(ellmer_web_content_methods()))

  turn <- ellmer::AssistantTurn(
    contents = list(
      ellmer::ContentToolRequestSearch(
        query = "shinychat structured blocks"
      ),
      ellmer::ContentText("According to the docs..."),
      ellmer::ContentCitation(
        source = ellmer::WebSource("https://example.com/docs", "Docs"),
        grounded_span = "According to the docs"
      )
    )
  )

  results <- contents_shinychat(turn)
  search_block <- Filter(
    function(x) {
      inherits(x, "shinychat_block") && identical(x$type, "web_search")
    },
    results
  )
  expect_length(search_block, 1L)
  expect_equal(
    search_block[[1]]$cited_sources,
    list(list(url = "https://example.com/docs", title = "Docs"))
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
    format(contents_shinychat(result))
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
        full_screen = FALSE,
        open_style = "minimal"
      ),
      class = "shinychat_tool_result_display"
    )
  )
})

test_that("tool_result_display() supports framed open style", {
  expect_equal(
    tool_result_display(open_style = "framed")$open_style,
    "framed"
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

test_that("as_tool_result_display() warns and drops invalid open_style", {
  expect_warning(
    display <- as_tool_result_display(list(open_style = "panel")),
    "open_style.*must be.*minimal.*framed"
  )
  expect_null(display$open_style)
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
  # Exact-name lookup: `$open` would partially match `open_style`
  expect_null(display[["open"]])
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
  expect_true(res$show_request)
  expect_false(res$expanded)
  expect_false(res$full_screen)

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
  expect_false(res_ok$show_request)
  expect_true(res_ok$expanded)
  expect_true(res_ok$full_screen)
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
})

test_that("invalid tool annotation grouping is dropped (no field emitted)", {
  local_shinychat_tool_display(opt = "rich")

  tool <- new_tool(annotations = list(grouping = "bogus"))
  result <- new_tool_result(
    value = "test",
    request = new_tool_request(tool = tool)
  )
  res <- contents_shinychat(result)

  expect_null(res$grouping)
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
  expect_equal(req_res$title, "Weather Tool")
  expect_equal(req_res$grouping, "all")

  tool_res <- contents_shinychat(result)
  expect_s3_class(tool_res, "shinychat_tool_result")
  expect_equal(tool_res$title, "Weather Tool")
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
