.onLoad <- function(libname, pkgname) {
  rlang::run_on_load()
  S7::methods_register()
  shiny::registerInputHandler(
    "shinychat.userInput",
    function(value, session, name) user_input_contents(value),
    force = TRUE
  )
  shiny::registerInputHandler(
    "shinychat.messages",
    function(value, session, name) messages_input_value(value),
    force = TRUE
  )
}

as_generator <- function(x) {
  if (inherits(x, "coro_generator_instance")) {
    x
  } else {
    coro::gen(yield(x))
  }
}

process_ui <- function(ui, session) {
  process_deps <- asNamespace("shiny")[["processDeps"]]
  if (!is.function(process_deps)) {
    stop(
      "Expected processDeps() function to exist in Shiny. Please report this issue."
    )
  }

  # Render UI to html and register dependencies with the session
  res <- with_current_theme({
    process_deps(ui, session)
  })

  # Remove html_dependency class so jsonlite can handle it
  res[["deps"]] <- lapply(res[["deps"]], unclass)
  res
}

# Serialize HTMLDependency objects for the wire through the session's
# processDeps (registering web-dependency routes and applying lib_prefix).
# Returns an empty list when there are no deps, so callers can put the
# result directly on a message envelope. Mirrors Python's
# serialize_html_deps (kata#rpx1).
serialize_html_deps <- function(deps, session) {
  if (length(deps) == 0) {
    return(list())
  }
  process_ui(htmltools::tagList(!!!deps), session)[["deps"]] %||% list()
}

# Session-free serialization of HTMLDependency objects, producing the wire
# shape the client's renderDependencies understands (mirrors shiny's
# createWebDependency(), but without its addResourcePath() side effect —
# there may be no running app at UI-construction time, and the dep objects
# also propagate as page-level dependencies, which Shiny's page render
# registers under the same "name-version" prefix). This is the no-session
# fallback for initial content-segments block entries (mirroring the raw
# as_dict() serialization Python's output_markdown_stream() uses,
# kata#rpx1).
serialize_html_deps_static <- function(deps) {
  lapply(deps, function(dep) {
    # Remove html_dependency class so jsonlite can handle it
    dep <- unclass(dep)
    if (is.null(dep$src) || is.null(dep$src$href)) {
      dep$src$href <- paste0(dep$name, "-", dep$version)
    }
    dep$src$file <- NULL
    dep
  })
}

# Compile HTMLDependency()s against the current/default theme
# (that is, compile Sass with Bootstrap Sass headers)
with_current_theme <- function(expr) {
  theme <- bslib::bs_current_theme() %||% bslib::bs_theme()
  old_theme <- bslib::bs_global_set(theme)
  on.exit(bslib::bs_global_set(old_theme), add = TRUE)
  force(expr)
}

tag_require <- function(tag, version = 5, caller = "") {
  tag_req <- asNamespace("bslib")[["tag_require"]]
  if (!is.function(tag_req)) {
    stop(
      "Expected tag_require() function to exist in bslib. Please report this issue."
    )
  }
  tag_req(tag, version, caller)
}
