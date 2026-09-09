test_elapsed_seconds <- function() {
  unname(proc.time()[["elapsed"]])
}

wait_until <- function(
  condition,
  timeout = 5,
  interval = 0.05,
  description = "condition"
) {
  deadline <- test_elapsed_seconds() + timeout

  repeat {
    if (isTRUE(condition())) {
      return(invisible(TRUE))
    }

    remaining <- deadline - test_elapsed_seconds()
    if (remaining <= 0) {
      break
    }
    later::run_now(min(interval, remaining))
  }

  testthat::fail(sprintf(
    "Timed out after %.1f seconds waiting for %s.",
    timeout,
    description
  ))
}

# Given a promise-yielding expression, loop until it resolves or rejects.
# DON'T USE THIS TECHNIQUE IN SHINY, PLUMBER, OR HTTPUV CONTEXTS.
sync <- function(expr, timeout = 10) {
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

  wait_until(
    function() done,
    timeout = timeout,
    description = "promise to settle"
  )

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
