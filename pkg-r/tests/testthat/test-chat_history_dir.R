# Mirror Posit Connect's write-once save.interface/load.interface hooks.
local_connect_like_hooks <- function(root, .env = parent.frame()) {
  save_interface <- function(id, callback) {
    dirname <- file.path(root, id)
    if (dir.exists(dirname)) {
      stop("Directory ", dirname, " already exists")
    }
    dir.create(dirname, recursive = TRUE)
    callback(dirname)
  }
  load_interface <- function(id, callback) {
    dirname <- file.path(root, id)
    if (!dir.exists(dirname)) {
      stop("Session ", id, " not found")
    }
    callback(dirname)
  }
  withr::local_options(
    list(
      shiny.save.interface = NULL,
      shiny.load.interface = NULL
    ),
    .local_envir = .env
  )
  shiny::shinyOptions(
    save.interface = save_interface,
    load.interface = load_interface
  )
  withr::defer(
    shiny::shinyOptions(save.interface = NULL, load.interface = NULL),
    envir = .env
  )
}

test_that("CONNECT_CONTENT_DATA_DIR wins", {
  root <- withr::local_tempdir()
  withr::local_envvar(CONNECT_CONTENT_DATA_DIR = root)
  expect_equal(
    resolve_history_dir(),
    file.path(root, "shinychat-conversations")
  )
})

test_that("bookmark hooks are used when registered", {
  withr::local_envvar(CONNECT_CONTENT_DATA_DIR = "")
  root <- withr::local_tempdir()
  local_connect_like_hooks(root)

  expect_equal(
    resolve_history_dir(),
    file.path(root, "shinychat-conversations")
  )
})

test_that("Connect-like hooks survive repeated sessions", {
  withr::local_envvar(CONNECT_CONTENT_DATA_DIR = "")
  root <- withr::local_tempdir()
  local_connect_like_hooks(root)

  first <- resolve_history_dir()
  second <- resolve_history_dir()

  expect_equal(first, second)
  expect_equal(first, file.path(root, "shinychat-conversations"))
  expect_true(dir.exists(first))
})

test_that("Connect-like hooks survive a lost creation race", {
  withr::local_envvar(CONNECT_CONTENT_DATA_DIR = "")
  root <- withr::local_tempdir()
  target <- file.path(root, "shinychat-conversations")

  shiny::shinyOptions(
    save.interface = function(id, callback) {
      # Another session won the race after our load attempt failed.
      dir.create(target, recursive = TRUE)
      stop("Directory ", target, " already exists")
    },
    load.interface = function(id, callback) {
      if (!dir.exists(target)) {
        stop("Session ", id, " not found")
      }
      callback(target)
    }
  )
  withr::defer(shiny::shinyOptions(
    save.interface = NULL,
    load.interface = NULL
  ))

  expect_equal(resolve_history_dir(), target)
})

test_that("falls back locally with a warning when the host disables bookmarking", {
  withr::local_envvar(CONNECT_CONTENT_DATA_DIR = "")
  not_configured <- function(id, callback) {
    stop("This server is not configured for saving sessions to disk.")
  }
  shiny::shinyOptions(
    save.interface = not_configured,
    load.interface = not_configured
  )
  withr::defer(shiny::shinyOptions(
    save.interface = NULL,
    load.interface = NULL
  ))

  expect_warning(
    dir <- resolve_history_dir(),
    "not configured for saving sessions"
  )
  expect_equal(dir, file.path(".shinychat", "conversations"))
})

test_that("falls back locally when no hooks are registered", {
  withr::local_envvar(CONNECT_CONTENT_DATA_DIR = "")
  shiny::shinyOptions(save.interface = NULL, load.interface = NULL)
  expect_equal(
    resolve_history_dir(),
    file.path(".shinychat", "conversations")
  )
})
