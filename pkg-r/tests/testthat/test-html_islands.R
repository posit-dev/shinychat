test_that("plain HTML becomes a single island item", {
  content <- htmltools::tagList(
    htmltools::div("hello"),
    htmltools::span("world")
  )
  result <- split_html_islands(content)
  expect_length(result, 1)
  expect_s3_class(result[[1]], "shinychat_island")
})

test_that("react element is emitted bare", {
  content <- htmltools::tag(
    "shiny-tool-result",
    list(`data-shinychat-react` = NA, `request-id` = "abc")
  )
  result <- split_html_islands(content)
  expect_length(result, 1)
  expect_s3_class(result[[1]], "shiny.tag")
  expect_false(inherits(result[[1]], "shinychat_island"))
})

test_that("mixed content splits around react elements", {
  content <- htmltools::tagList(
    htmltools::div("before"),
    htmltools::tag(
      "shiny-tool-result",
      list(`data-shinychat-react` = NA, `request-id` = "abc")
    ),
    htmltools::div("after")
  )
  result <- split_html_islands(content)
  expect_length(result, 3)
  expect_s3_class(result[[1]], "shinychat_island")
  expect_s3_class(result[[2]], "shiny.tag")
  expect_s3_class(result[[3]], "shinychat_island")
})

test_that("adjacent react elements produce no empty islands", {
  content <- htmltools::tagList(
    htmltools::tag("shiny-tool-request", list(`data-shinychat-react` = NA)),
    htmltools::tag("shiny-tool-result", list(`data-shinychat-react` = NA))
  )
  result <- split_html_islands(content)
  expect_length(result, 2)
  expect_true(all(vapply(
    result,
    function(item) inherits(item, "shiny.tag"),
    logical(1)
  )))
})

test_that("single tag without react attr becomes an island item", {
  result <- split_html_islands(htmltools::div("hello"))
  expect_length(result, 1)
  expect_s3_class(result[[1]], "shinychat_island")
})

test_that("empty tagList returns empty list without error", {
  result <- split_html_islands(htmltools::tagList())
  expect_equal(result, list())
})

test_that("plain HTML derives a single block part (no island tag)", {
  content <- htmltools::tagList(
    htmltools::div("hello"),
    htmltools::span("world")
  )
  parts <- derive_island_parts(content)
  expect_length(parts, 1)
  expect_s3_class(parts[[1]], "shinychat_island_block_part")
  expect_match(parts[[1]]$html, "<div>hello</div>", fixed = TRUE)
  expect_match(parts[[1]]$html, "<span>world</span>", fixed = TRUE)
  expect_no_match(parts[[1]]$html, "shiny-chat-raw-html", fixed = TRUE)
})

test_that("react element derives a residual part rendered bare", {
  content <- htmltools::tag(
    "shiny-tool-result",
    list(`data-shinychat-react` = NA, `request-id` = "abc")
  )
  parts <- derive_island_parts(content)
  expect_length(parts, 1)
  expect_s3_class(parts[[1]], "shinychat_island_residual_part")
  expect_match(parts[[1]]$html, "shiny-tool-result", fixed = TRUE)
  expect_match(parts[[1]]$html, "data-shinychat-react", fixed = TRUE)
  expect_no_match(parts[[1]]$html, "shiny-chat-raw-html", fixed = TRUE)
  expect_match(parts[[1]]$html, "^\n\n")
  expect_match(parts[[1]]$html, "\n\n$")
})

test_that("mixed content derives block parts around a residual run", {
  content <- htmltools::tagList(
    htmltools::div("before"),
    htmltools::tag(
      "shiny-tool-result",
      list(`data-shinychat-react` = NA, `request-id` = "abc")
    ),
    htmltools::div("after")
  )
  parts <- derive_island_parts(content)
  expect_length(parts, 3)
  expect_s3_class(parts[[1]], "shinychat_island_block_part")
  expect_s3_class(parts[[2]], "shinychat_island_residual_part")
  expect_s3_class(parts[[3]], "shinychat_island_block_part")
  expect_equal(parts[[1]]$html, "<div>before</div>")
  expect_equal(parts[[3]]$html, "<div>after</div>")
  expect_match(parts[[2]]$html, "shiny-tool-result", fixed = TRUE)
  expect_no_match(parts[[1]]$html, "shiny-tool-result", fixed = TRUE)
  expect_no_match(parts[[3]]$html, "shiny-tool-result", fixed = TRUE)
})

test_that("adjacent react elements coalesce into one residual run", {
  content <- htmltools::tagList(
    htmltools::tag("shiny-tool-request", list(`data-shinychat-react` = NA)),
    htmltools::tag("shiny-tool-result", list(`data-shinychat-react` = NA))
  )
  parts <- derive_island_parts(content)
  expect_length(parts, 1)
  expect_s3_class(parts[[1]], "shinychat_island_residual_part")
  expect_match(parts[[1]]$html, "shiny-tool-request", fixed = TRUE)
  expect_match(parts[[1]]$html, "shiny-tool-result", fixed = TRUE)
})

test_that("single tag without react attr derives a block part", {
  parts <- derive_island_parts(htmltools::div("hello"))
  expect_length(parts, 1)
  expect_s3_class(parts[[1]], "shinychat_island_block_part")
  expect_equal(parts[[1]]$html, "<div>hello</div>")
})

test_that("bare string content raises", {
  expect_error(derive_island_parts("hello world"), "trusted tag content")
})

test_that("HTML-marked string derives a block part", {
  parts <- derive_island_parts(htmltools::HTML("<b>hello</b>"))
  expect_length(parts, 1)
  expect_s3_class(parts[[1]], "shinychat_island_block_part")
  expect_match(parts[[1]]$html, "<b>hello</b>", fixed = TRUE)
})

test_that("island parts carry dependency objects", {
  dep <- htmltools::htmlDependency(
    "island-dep",
    "1.0.0",
    src = ".",
    script = "island.js"
  )
  parts <- derive_island_parts(htmltools::tagList(htmltools::div("x"), dep))
  expect_length(parts, 1)
  expect_s3_class(parts[[1]], "shinychat_island_block_part")
  dep_names <- vapply(parts[[1]]$deps, `[[`, character(1), "name")
  expect_true("island-dep" %in% dep_names)
})

test_that("render_island_string() flattens parts to one trusted string", {
  content <- htmltools::tagList(
    htmltools::div("before"),
    htmltools::tag(
      "shiny-tool-result",
      list(`data-shinychat-react` = NA, `request-id` = "abc")
    ),
    htmltools::div("after")
  )
  rendered <- render_island_string(content)
  expect_match(rendered$html, "<div>before</div>", fixed = TRUE)
  expect_match(rendered$html, "shiny-tool-result", fixed = TRUE)
  expect_match(rendered$html, "<div>after</div>", fixed = TRUE)
  expect_no_match(rendered$html, "shiny-chat-raw-html", fixed = TRUE)
  expect_equal(rendered$deps, list())
})

test_that("render_island_string() collects dependency objects", {
  dep <- htmltools::htmlDependency(
    "flatten-dep",
    "1.0.0",
    src = ".",
    script = "flatten.js"
  )
  rendered <- render_island_string(htmltools::div("x", dep))
  dep_names <- vapply(rendered$deps, `[[`, character(1), "name")
  expect_true("flatten-dep" %in% dep_names)
})

test_that("mixed tagList provenance is tracked per leaf", {
  segments <- split_content_by_trust(
    htmltools::tagList(
      "## This is markdown",
      htmltools::div("This is HTML")
    )
  )

  expect_length(segments, 2)
  expect_false(segments[[1]]$trusted)
  expect_identical(segments[[1]]$content, "## This is markdown")
  expect_true(segments[[2]]$trusted)
})

test_that("HTML-marked strings are trusted independently of plain strings", {
  segments <- split_content_by_trust(
    htmltools::tagList(
      "model text",
      htmltools::HTML("<strong>server HTML</strong>")
    )
  )

  expect_identical(
    vapply(segments, `[[`, logical(1), "trusted"),
    c(FALSE, TRUE)
  )
})

test_that("render_island_string() mixed content escapes bare string HTML", {
  # A bare string with executable HTML in mixed content is HTML-escaped
  # (safe for the single-string innerHTML payload), while trusted tags
  # render as real HTML.
  rendered <- render_island_string(
    htmltools::tagList(
      "<img src=x onerror=alert(1)>",
      htmltools::tags$b("bold")
    )
  )
  # Bare string is HTML-escaped — executable HTML is neutralized.
  expect_match(rendered$html, "&lt;img", fixed = TRUE)
  expect_no_match(rendered$html, "<img src=x onerror", fixed = TRUE)
  # Tag is rendered as HTML.
  expect_match(rendered$html, "<b>bold</b>", fixed = TRUE)
  expect_no_match(rendered$html, "shiny-chat-raw-html", fixed = TRUE)
})

test_that("render_island_string() pure tag content is unchanged", {
  # Pure tag content (no bare strings) should behave exactly as before:
  # all trusted, rendered through derive_island_parts().
  rendered <- render_island_string(
    htmltools::tagList(
      htmltools::div("before"),
      htmltools::tag(
        "shiny-tool-result",
        list(`data-shinychat-react` = NA, `request-id` = "abc")
      ),
      htmltools::div("after")
    )
  )
  expect_match(rendered$html, "<div>before</div>", fixed = TRUE)
  expect_match(rendered$html, "shiny-tool-result", fixed = TRUE)
  expect_match(rendered$html, "<div>after</div>", fixed = TRUE)
  expect_no_match(rendered$html, "shiny-chat-raw-html", fixed = TRUE)
  expect_equal(rendered$deps, list())
})

test_that("render_island_string() pure string content is escaped", {
  # A bare string (not HTML()-marked) is HTML-escaped by renderTags (safe
  # for the single-string innerHTML payload).
  rendered <- render_island_string("<img src=x onerror=alert(1)>")
  expect_match(rendered$html, "&lt;img", fixed = TRUE)
  expect_no_match(rendered$html, "<img src=x onerror", fixed = TRUE)
  expect_equal(rendered$deps, list())
})

test_that("render_island_string() HTML()-marked string is trusted and raw", {
  # HTML()-marked strings are trusted and should pass through as-is (they
  # are already HTML, not escaped by renderTags).
  rendered <- render_island_string(htmltools::HTML("<b>raw</b>"))
  expect_match(rendered$html, "<b>raw</b>", fixed = TRUE)
  expect_equal(rendered$deps, list())
})

test_that("render_island_string() mixed content preserves ordering", {
  rendered <- render_island_string(
    htmltools::tagList(
      htmltools::div("first"),
      "<img src=x onerror=alert(1)>",
      htmltools::span("last")
    )
  )
  # Order: first tag, escaped bare string, last tag
  expect_match(rendered$html, "<div>first</div>", fixed = TRUE)
  expect_match(rendered$html, "&lt;img", fixed = TRUE)
  expect_match(rendered$html, "<span>last</span>", fixed = TRUE)
  # Verify ordering: first before escaped-string before last
  first_pos <- regexpr("<div>first</div>", rendered$html, fixed = TRUE)
  middle_pos <- regexpr("&lt;img", rendered$html, fixed = TRUE)
  last_pos <- regexpr("<span>last</span>", rendered$html, fixed = TRUE)
  expect_true(first_pos < middle_pos)
  expect_true(middle_pos < last_pos)
})
