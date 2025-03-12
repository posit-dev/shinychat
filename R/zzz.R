.onLoad <- function(libname, pkgname) {
  rlang::run_on_load()
}

as_generator <- function(x) {
  if (inherits(x, "coro_generator_instance")) {
    x
  } else {
    coro::gen(yield(x))
  }
}

process_ui <- function(ui, session) {
  process_deps <- getFromNamespace("processDeps", "shiny")
  if (!is.function(process_deps)) {
    stop("Expected processDeps() function to exist in Shiny. Please report this issue.")
  }

  # Render UI to html and register dependencies with the session
  res <- with_current_theme({
    process_deps(ui, session)
  })

  # Remove html_dependency class so jsonlite can handle it
  res[["deps"]] <- lapply(res[["deps"]], unclass)
  res
}

# Compile HTMLDependency()s against the current/default theme
# (that is, compile Sass with Bootstrap Sass headers)
with_current_theme <- function(expr) {
  theme <- bslib::bs_current_theme() %||% bslib::bs_theme()
  old_theme <- bslib::bs_global_set(theme)
  on.exit(bslib::bs_global_set(old_theme), add = TRUE)
  expr
}

tag_require <- function(tag, version = 5, caller = "") {
  tag_req <- getFromNamespace("tag_require", "bslib")
  if (!is.function(tag_req)) {
    stop("Expected tag_require() function to exist in bslib. Please report this issue.")
  }
  tag_req(tag, version, caller)
}
