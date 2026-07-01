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

# file.rename() fails to overwrite an existing `to` on Windows, unlike POSIX.
# Try rename first since it's atomic and (same-filesystem) metadata-only, so
# the common case stays cheap; only fall back to copy + remove -- which reads
# and rewrites the whole file and briefly leaves `to` in a partial state if
# interrupted -- when rename can't do it.
file_move <- function(from, to) {
  if (suppressWarnings(file.rename(from, to))) {
    return(invisible(TRUE))
  }
  if (dir.exists(to)) {
    # file.copy() would copy `from` *into* `to` rather than fail
    return(invisible(FALSE))
  }

  ok <- file.copy(from, to, overwrite = TRUE)
  if (ok) {
    unlink(from)
  }
  invisible(ok)
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
