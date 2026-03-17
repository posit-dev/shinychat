test_that("plain HTML gets a single shinychat-raw-html wrapper", {
  content <- htmltools::tagList(
    htmltools::div("hello"),
    htmltools::span("world")
  )
  result <- split_html_islands(content)
  rendered <- as.character(htmltools::tagList(result))
  expect_equal(
    length(grep("<shinychat-raw-html>", strsplit(rendered, "\n")[[1]])),
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
  expect_no_match(rendered, "shinychat-raw-html")
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
  matches <- gregexpr("<shinychat-raw-html>", rendered)[[1]]
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
  expect_no_match(rendered, "shinychat-raw-html")
})

test_that("single tag without react attr gets wrapped", {
  content <- htmltools::div("hello")
  result <- split_html_islands(content)
  rendered <- as.character(htmltools::tagList(result))
  expect_match(rendered, "shinychat-raw-html")
})
