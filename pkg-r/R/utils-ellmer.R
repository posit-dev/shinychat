as_ellmer_turns <- function(messages) {
  if (is.null(messages) || length(messages) == 0) {
    return(list())
  }

  map(messages, function(msg) {
    ellmer::Turn(
      role = msg$role,
      contents = list(ellmer::ContentText(msg$content))
    )
  })
}
