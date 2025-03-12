render_tags <- function(ui) {
  res <- htmltools::renderTags(ui)

  deps <- lapply(res$dependencies, function(x) {
    x$version <- NULL
    x$src <- NULL
    unclass(x[!vapply(x, is.null, logical(1))])
  })

  list(
    deps = jsonlite::toJSON(deps, auto_unbox = TRUE),
    html = res$html
  )
}