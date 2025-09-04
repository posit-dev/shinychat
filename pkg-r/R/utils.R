sanitized_chat_error <- function(err) {
  needs_sanitized <-
    isTRUE(getOption("shiny.sanitize.errors")) &&
    !inherits(err, "shiny.custom.error")

  if (needs_sanitized) {
    "\n\n**An error occurred.** Please try again or contact the app author."
  } else {
    sprintf(
      "\n\n**An error occurred:**\n\n```\n%s\n```",
      strip_ansi(conditionMessage(err))
    )
  }
}

strip_ansi <- function(text) {
  # Matches codes like "\x1B[31;43m", "\x1B[1;3;4m"
  ansi_pattern <- "(\x1B|\x033)\\[[0-9;?=<>]*[@-~]"
  gsub(ansi_pattern, "", text)
}


drop_nulls <- function(x) {
  x[!vapply(x, is.null, FUN.VALUE = logical(1))]
}

html_escape <- function(x, attr = TRUE) {
  x <- gsub("&", "&amp;", x, fixed = TRUE)
  x <- gsub("<", "&lt;", x, fixed = TRUE)
  x <- gsub(">", "&gt;", x, fixed = TRUE)
  if (attr) {
    x <- gsub("\"", "&quot;", x, fixed = TRUE)
    x <- gsub("\r", "&#13;", x, fixed = TRUE)
    x <- gsub("\n", "&#10;", x, fixed = TRUE)
  }
  x
}
