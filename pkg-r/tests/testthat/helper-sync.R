# Given a promise-yielding expression, loop until it resolves or rejects.
# DON'T USE THIS TECHNIQUE IN SHINY, PLUMBER, OR HTTPUV CONTEXTS.
sync <- function(expr) {
  p <- force(expr)

  done <- FALSE
  success <- NULL
  error <- NULL

  promises::then(
    p,
    function(result) {
      success <<- result
      done <<- TRUE
    },
    function(err) {
      error <<- err
      done <<- TRUE
    }
  )

  while (!done) {
    later::run_now(0.25)
  }
  if (!is.null(error)) {
    stop(error)
  } else {
    success
  }
}

expect_promise <- function(p, state = NULL) {
  name <- deparse(substitute(p))
  expect(
    promises::is.promise(p),
    sprintf("`%s` is not a promise", name)
  )
  if (!is.null(state)) {
    expect_equal(attr(p, "promise_impl")$status(), state)
  }
}
