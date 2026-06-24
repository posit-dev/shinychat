needs_sanitized <- function(err) {
  isTRUE(getOption("shiny.sanitize.errors")) &&
    !inherits(err, "shiny.custom.error")
}

sanitized_error_message <- function(err) {
  if (needs_sanitized(err)) {
    "An error occurred. Please try again or contact the app author."
  } else {
    strip_ansi(conditionMessage(err))
  }
}

notify_error <- function(prefix, err) {
  shiny::showNotification(
    paste0(prefix, ": ", sanitized_error_message(err)),
    type = "error",
    duration = NULL
  )
  rlang::warn(prefix, parent = err)
}

sanitized_chat_error <- function(err) {
  if (needs_sanitized(err)) {
    sprintf("\n\n**%s**", sanitized_error_message(err))
  } else {
    sprintf(
      "\n\n**An error occurred:**\n\n```\n%s\n```",
      sanitized_error_message(err)
    )
  }
}

strip_ansi <- function(text) {
  # Matches codes like "\x1B[31;43m", "\x1B[1;3;4m"
  ansi_pattern <- "(\x1B|\x033)\\[[0-9;?=<>]*[@-~]"
  gsub(ansi_pattern, "", text)
}

shinychat_deps <- function() {
  htmltools::htmlDependency(
    "shinychat",
    utils::packageVersion("shinychat"),
    package = "shinychat",
    src = "lib/shiny",
    script = list(src = "shinychat.js", type = "module"),
    stylesheet = "shinychat.css"
  )
}

drop_nulls <- function(x) {
  x[!vapply(x, is.null, FUN.VALUE = logical(1))]
}
