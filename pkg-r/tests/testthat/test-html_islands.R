test_that("plain HTML gets a single shiny-chat-raw-html wrapper", {
  content <- htmltools::tagList(
    htmltools::div("hello"),
    htmltools::span("world")
  )
  result <- split_html_islands(content)
  rendered <- as.character(htmltools::tagList(result))
  expect_equal(
    length(grep("<shiny-chat-raw-html>", strsplit(rendered, "\n")[[1]])),
    1
  )
  expect_match(rendered, "<div>hello</div>")
  expect_match(rendered, "<span>world</span>")
})

test_that("react element is emitted bare", {
  content <- htmltools::tag(
    "shiny-tool-result",
    list(`data-shinychat-react` = NA, `request-id` = "abc")
  )
  result <- split_html_islands(content)
  rendered <- as.character(htmltools::tagList(result))
  expect_no_match(rendered, "shiny-chat-raw-html")
  expect_match(rendered, "shiny-tool-result")
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
  rendered <- as.character(htmltools::tagList(result))
  matches <- gregexpr("<shiny-chat-raw-html>", rendered)[[1]]
  expect_equal(sum(matches > 0), 2)
  expect_match(rendered, "shiny-tool-result")
})

test_that("adjacent react elements produce no empty islands", {
  content <- htmltools::tagList(
    htmltools::tag("shiny-tool-request", list(`data-shinychat-react` = NA)),
    htmltools::tag("shiny-tool-result", list(`data-shinychat-react` = NA))
  )
  result <- split_html_islands(content)
  rendered <- as.character(htmltools::tagList(result))
  expect_no_match(rendered, "shiny-chat-raw-html")
})

test_that("single tag without react attr gets wrapped", {
  content <- htmltools::div("hello")
  result <- split_html_islands(content)
  rendered <- as.character(htmltools::tagList(result))
  expect_match(rendered, "shiny-chat-raw-html")
})

test_that("empty tagList returns empty list without error", {
  result <- split_html_islands(htmltools::tagList())
  expect_equal(result, list())
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
