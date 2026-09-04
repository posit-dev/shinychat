#' @keywords internal
"_PACKAGE"

## usethis namespace: start
#' @import rlang
#' @importFrom S7 new_generic method "method<-" new_property S7_dispatch S7_inherits
#' @importFrom coro async
#' @importFrom htmltools as.tags
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
  ellmer::contents_html
}

release_bullets <- function() {
  c(
    "Check that shinychat js assets are up-to-date (`make js-build && make r-update-dist`)",
    "Run `make r-vignette-screenshots` to refresh the tool-ui vignette screenshots so they match the current UI"
  )
}
