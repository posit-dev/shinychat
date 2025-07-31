#' @keywords internal
"_PACKAGE"

## usethis namespace: start
#' @import rlang
#' @import S7
#' @importFrom coro async
#' @importFrom htmltools tag css HTML
#' @importFrom lifecycle deprecated
## usethis namespace: end
NULL

# enable usage of <S7_object>@name in package code
#' @rawNamespace if (getRversion() < "4.3.0") importFrom("S7", "@")
NULL

ignore_unused_imports <- function() {
  jsonlite::fromJSON
  fastmap::fastqueue
}

release_bullets <- function() {
  c(
    "Check that shinychat js assets are up-to-date (`scripts/update-chat.sh`)"
  )
}
