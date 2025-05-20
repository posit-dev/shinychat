#' @keywords internal
"_PACKAGE"

## usethis namespace: start
#' @importFrom coro async
#' @importFrom htmltools tag css HTML
#' @import rlang
## usethis namespace: end
NULL

ignore_unused_imports <- function() {
  jsonlite::fromJSON
  fastmap::fastqueue
  ellmer::contents_html
}

release_bullets <- function() {
  c(
    "Check that shinychat js assets are up-to-date (`scripts/update-chat.sh`)"
  )
}
