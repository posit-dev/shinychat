#' Create a chat sidebar configuration
#'
#' @param ... UI content to display in the sidebar.
#' @param history Whether to display the chat history selector in the sidebar.
#' @param width The initial sidebar width. Positive numbers are converted to
#'   pixels; character values must be valid CSS lengths.
#' @param open The initial sidebar state. One of `"auto"`, `"open"`, `"closed"`,
#'   or `"always"`. Logical values are aliases for `"open"` and `"closed"`.
#' @param resizable Whether the sidebar can be resized on desktop.
#'
#' @returns A configuration object for use with [chat_nav_panel()].
#' @export
chat_sidebar <- function(
  ...,
  history = FALSE,
  width = 280,
  open = "auto",
  resizable = TRUE
) {
  content <- chat_config_content(...)
  chat_validate_boolean(history, "history")
  width <- chat_validate_width(width, "width")
  open <- chat_normalize_sidebar_open(open)
  chat_validate_boolean(resizable, "resizable")

  structure(
    list(
      content = content,
      history = history,
      width = width,
      open = open,
      resizable = resizable
    ),
    class = "chat_sidebar"
  )
}

#' Create a chat artifact configuration
#'
#' @param ... UI content to display in the artifact panel.
#' @param title An optional artifact title.
#' @param width The initial artifact width. Positive numbers are converted to
#'   pixels; character values must be valid CSS lengths.
#' @param open Whether the artifact is initially visible.
#' @param resizable Whether the artifact can be resized on desktop.
#'
#' @returns A configuration object for use with [chat_ui()].
#' @export
chat_artifact <- function(
  ...,
  title = NULL,
  width = 400,
  open = FALSE,
  resizable = TRUE
) {
  content <- chat_config_content(...)
  if (!is.null(title)) {
    chat_validate_string(title, "title", allow_empty = TRUE)
  }
  width <- chat_validate_width(width, "width")
  chat_validate_boolean(open, "open")
  chat_validate_boolean(resizable, "resizable")

  structure(
    list(
      content = content,
      title = title,
      width = width,
      open = open,
      resizable = resizable
    ),
    class = "chat_artifact"
  )
}

#' Create a page-chat navigation panel
#'
#' @param title The panel title.
#' @param ... UI content to display when the panel is active.
#' @param value An optional unique navigation value.
#' @param icon An optional icon to display with the title.
#' @param sidebar Whether to use the default sidebar (`TRUE`), no
#'   page-specific sidebar (`FALSE`), or a [chat_sidebar()] configuration.
#'
#' @returns A configuration object for use with `page_chat()`.
#' @export
chat_nav_panel <- function(
  title,
  ...,
  value = NULL,
  icon = NULL,
  sidebar = FALSE
) {
  chat_validate_string(title, "title")
  content <- chat_config_content(...)
  if (!is.null(value)) {
    chat_validate_string(value, "value")
  }
  chat_validate_sidebar(sidebar)

  structure(
    list(
      title = title,
      content = content,
      value = value,
      icon = icon,
      sidebar = sidebar
    ),
    class = "chat_nav_panel"
  )
}

#' Create a chat history selector
#'
#' @param id The ID of the associated chat.
#' @param ... Named HTML attributes to apply to the selector.
#'
#' @returns A Shiny tag object.
#' @export
chat_ui_history <- function(id, ...) {
  attrs <- rlang::list2(...)
  if (!all(nzchar(rlang::names2(attrs)))) {
    rlang::abort("All arguments in ... must be named HTML attributes.")
  }
  if ("for" %in% names(attrs)) {
    rlang::abort(
      "`for` is managed by chat_ui_history(); supply the associated chat ID with `id`."
    )
  }

  chat_ui_history_tag(resolve_id(id), attrs)
}

#' Create a full-window chat page
#'
#' `page_chat()` creates a fillable page containing one persistent [chat_ui()]
#' home view, optional navigation pages, and a responsive app-menu sidebar.
#'
#' @param title The display title. May be text or reactive/static UI.
#' @param icon Optional UI displayed before `title`.
#' @param ... Named lower-frequency [chat_ui()] arguments and HTML attributes.
#'   `page_chat()` owns `height`, `fill`, and `show_history`; attempts to pass
#'   those arguments are rejected.
#' @param id A non-empty string identifying the chat.
#' @param pages `NULL` or a list of [chat_nav_panel()] configurations.
#' @param toolbar Optional UI displayed with the page navigation controls.
#' @param sidebar Whether to use the default history sidebar (`TRUE`), omit the
#'   default sidebar (`FALSE`), or use a [chat_sidebar()] configuration.
#' @param messages,greeting,placeholder,width,icon_assistant,enable_cancel,allow_attachments,footer,artifact
#'   Common arguments passed to [chat_ui()].
#' @param window_title A static browser-window title. The default, `NA`,
#'   derives the window title from `title` when `title` is a scalar string.
#'   Use `NULL` to omit the window title.
#' @param lang An optional non-empty document language string.
#' @param theme A [bslib::bs_theme()] object.
#'
#' @returns A fillable bslib page.
#' @export
page_chat <- function(
  title,
  icon = NULL,
  ...,
  id = "chat",
  pages = NULL,
  toolbar = NULL,
  sidebar = TRUE,
  messages = NULL,
  greeting = NULL,
  placeholder = "Enter a message...",
  width = "min(680px, 100%)",
  icon_assistant = NULL,
  enable_cancel = NULL,
  allow_attachments = NULL,
  footer = NULL,
  artifact = TRUE,
  window_title = NA,
  lang = NULL,
  theme = bslib::bs_theme()
) {
  dots <- rlang::list2(...)
  dot_names <- rlang::names2(dots)
  if (any(!nzchar(dot_names))) {
    cli::cli_abort(
      "Only {.arg title} and {.arg icon} may be supplied positionally."
    )
  }

  owned_args <- intersect(
    unique(dot_names),
    c("height", "fill", "show_history")
  )
  if (length(owned_args) > 0) {
    cli::cli_abort(c(
      "{.fn page_chat} owns {.arg {owned_args}}.",
      i = "Remove {cli::qty(owned_args)}the supplied argument{?s}; the page always uses {.code height = \"100%\"}, {.code fill = TRUE}, and {.code show_history = FALSE}."
    ))
  }

  chat_validate_plain_string(id, "id")
  chat_validate_page_ui(title, "title", allow_null = FALSE)
  if (
    rlang::is_string(title) &&
      !inherits(title, "html") &&
      !nzchar(trimws(title))
  ) {
    cli::cli_abort("{.arg title} must not be an empty string.")
  }
  chat_validate_page_ui(icon, "icon")
  chat_validate_page_ui(toolbar, "toolbar")
  chat_validate_sidebar(sidebar)
  if (inherits(sidebar, "chat_sidebar")) {
    sidebar <- normalize_chat_sidebar_config(sidebar)
  }
  pages <- normalize_chat_pages(pages)
  window_title <- normalize_chat_window_title(window_title, title)
  if (!is.null(lang)) {
    chat_validate_plain_string(lang, "lang")
  }

  resolved_id <- resolve_id(id)
  chat <- rlang::exec(
    chat_ui,
    resolved_id,
    !!!dots,
    messages = messages,
    greeting = greeting,
    placeholder = placeholder,
    width = width,
    height = "100%",
    fill = TRUE,
    icon_assistant = icon_assistant,
    enable_cancel = enable_cancel,
    allow_attachments = allow_attachments,
    footer = footer,
    artifact = artifact,
    show_history = FALSE
  )
  sidebar_id <- paste0(resolved_id, "-sidebar")

  normalized <- normalize_page_sidebars(
    pages,
    sidebar,
    resolved_id
  )
  active_sidebar <- sidebar_metadata(normalized$home_sidebar)

  controls <- htmltools::tags$div(
    class = "shiny-chat-page-controls",
    htmltools::tags$nav(
      class = "shiny-chat-page-nav",
      `aria-label` = "Pages",
      lapply(normalized$pages, page_chat_nav_control)
    ),
    htmltools::tags$div(
      class = "shiny-chat-page-toolbar",
      toolbar
    )
  )

  identity <- if (length(pages) > 0) {
    htmltools::tags$button(
      type = "button",
      class = "shiny-chat-page-identity",
      `data-page-home` = "",
      `aria-label` = "Return to chat",
      page_chat_identity_content(icon, title)
    )
  } else {
    htmltools::tags$div(
      class = "shiny-chat-page-identity",
      page_chat_identity_content(icon, title)
    )
  }

  sidebar_panels <- lapply(
    normalized$sidebars,
    function(panel) {
      page_chat_sidebar_panel(
        panel$config,
        panel$key,
        resolved_id,
        hidden = !identical(panel$key, normalized$home_sidebar_key)
      )
    }
  )

  nav_sections <- Map(
    function(panel, normalized) {
      htmltools::tags$section(
        class = "shiny-chat-page-panel",
        id = normalized$panel_id,
        `aria-labelledby` = normalized$nav_id,
        `data-page-value` = normalized$value,
        `data-page-title` = panel$title,
        `data-sidebar-key` = normalized$sidebar_key,
        hidden = NA,
        !!!panel$content
      )
    },
    pages,
    normalized$pages
  )

  root <- htmltools::tag(
    "shiny-chat-page",
    list(
      `data-chat-id` = resolved_id,
      `data-active-page` = "home",
      htmltools::tags$header(
        class = "shiny-chat-page-header",
        htmltools::tags$button(
          type = "button",
          class = "shiny-chat-page-sidebar-toggle navbar-toggler",
          `aria-controls` = sidebar_id,
          `aria-expanded` = if (
            !is.null(normalized$home_sidebar) &&
              normalized$home_sidebar$open %in% c("open", "always")
          ) {
            "true"
          } else {
            "false"
          },
          `aria-label` = "Toggle app menu",
          htmltools::tags$span(class = "navbar-toggler-icon")
        ),
        identity,
        htmltools::tags$div(
          class = paste(
            "shiny-chat-page-controls-mount",
            "shiny-chat-page-controls-mount-desktop"
          ),
          controls
        )
      ),
      htmltools::tags$div(
        class = "shiny-chat-page-body",
        htmltools::tags$aside(
          id = sidebar_id,
          class = "shiny-chat-page-sidebar",
          `aria-label` = "App menu",
          `data-sidebar-key` = normalized$home_sidebar_key,
          `data-sidebar-open` = active_sidebar$open,
          `data-sidebar-width` = active_sidebar$width,
          `data-sidebar-resizable` = active_sidebar$resizable,
          htmltools::tags$div(
            class = paste(
              "shiny-chat-page-controls-mount",
              "shiny-chat-page-controls-mount-mobile"
            )
          ),
          sidebar_panels
        ),
        htmltools::tags$main(
          class = "shiny-chat-page-main",
          htmltools::tags$section(
            class = "shiny-chat-page-panel shiny-chat-page-home",
            `data-page-value` = "home",
            `data-sidebar-key` = normalized$home_sidebar_key,
            chat
          ),
          nav_sections
        )
      )
    )
  )

  root <- tag_require(root, version = 5, caller = "page_chat")

  bslib::page_fillable(
    root,
    fillable_mobile = TRUE,
    padding = 0,
    gap = 0,
    title = window_title,
    theme = theme,
    lang = lang
  )
}

chat_ui_history_tag <- function(id, attrs = list()) {
  htmltools::tag(
    "shiny-chat-history",
    rlang::list2(
      `for` = id,
      !!!attrs,
      shinychat_deps()
    )
  )
}

normalize_chat_pages <- function(pages) {
  if (is.null(pages)) {
    return(list())
  }
  if (!is.list(pages) || inherits(pages, "chat_nav_panel")) {
    cli::cli_abort(
      "{.arg pages} must be {.code NULL} or a list of {.fn chat_nav_panel} configurations."
    )
  }

  valid <- vapply(pages, inherits, logical(1), what = "chat_nav_panel")
  if (!all(valid)) {
    cli::cli_abort(
      "{.arg pages} item {which(!valid)[1]} must be a {.fn chat_nav_panel} configuration."
    )
  }

  for (i in seq_along(pages)) {
    page <- pages[[i]]
    chat_validate_plain_string(page$title, paste0("pages[[", i, "]]$title"))
    if (!is.null(page$value)) {
      chat_validate_plain_string(page$value, paste0("pages[[", i, "]]$value"))
    }
    if (!is.list(page$content)) {
      arg <- paste0("pages[[", i, "]]$content")
      cli::cli_abort(
        "{.arg {arg}} must be a list of UI content."
      )
    }
    chat_validate_page_ui(page$icon, paste0("pages[[", i, "]]$icon"))
    chat_validate_sidebar(page$sidebar)
    if (inherits(page$sidebar, "chat_sidebar")) {
      pages[[i]]$sidebar <- normalize_chat_sidebar_config(page$sidebar)
    }
  }

  values <- vapply(
    pages,
    function(page) {
      page$value %||% page$title
    },
    character(1)
  )
  if ("home" %in% values) {
    cli::cli_abort(
      "{.val home} is reserved for the chat home and cannot be used as a page value."
    )
  }
  duplicate <- duplicated(values)
  if (any(duplicate)) {
    cli::cli_abort(
      "Each navigation page must have a unique value; {.val {values[which(duplicate)[1]]}} is duplicated."
    )
  }

  pages
}

normalize_chat_sidebar_config <- function(sidebar) {
  required <- c("content", "history", "width", "open", "resizable")
  if (!is.list(sidebar) || !all(required %in% names(sidebar))) {
    cli::cli_abort(
      "A {.fn chat_sidebar} configuration must contain {.field {required}}."
    )
  }
  if (
    !is.list(sidebar$content) || any(nzchar(rlang::names2(sidebar$content)))
  ) {
    cli::cli_abort(
      "A {.fn chat_sidebar} configuration's {.field content} must be unnamed UI content."
    )
  }
  chat_validate_page_ui(sidebar$content, "sidebar$content")

  rlang::exec(
    chat_sidebar,
    !!!sidebar$content,
    history = sidebar$history,
    width = sidebar$width,
    open = sidebar$open,
    resizable = sidebar$resizable
  )
}

normalize_page_sidebars <- function(pages, sidebar, resolved_id) {
  use_default <- isTRUE(sidebar) ||
    any(vapply(
      pages,
      function(page) isTRUE(page$sidebar),
      logical(1)
    ))
  default_sidebar <- if (use_default) chat_sidebar(history = TRUE)
  home_sidebar <- if (isTRUE(sidebar)) {
    default_sidebar
  } else if (isFALSE(sidebar)) {
    NULL
  } else {
    sidebar
  }
  home_sidebar_key <- if (isTRUE(sidebar)) {
    "default"
  } else if (inherits(sidebar, "chat_sidebar")) {
    "home"
  }

  normalized_pages <- vector("list", length(pages))
  sidebars <- list()
  if (!is.null(default_sidebar)) {
    sidebars[[length(sidebars) + 1]] <- list(
      key = "default",
      config = default_sidebar
    )
  }
  if (inherits(sidebar, "chat_sidebar")) {
    sidebars[[length(sidebars) + 1]] <- list(
      key = "home",
      config = sidebar
    )
  }

  for (i in seq_along(pages)) {
    page <- pages[[i]]
    value <- page$value %||% page$title
    sidebar_key <- if (isTRUE(page$sidebar)) {
      "default"
    } else if (isFALSE(page$sidebar)) {
      NULL
    } else {
      key <- paste0("page-", i)
      sidebars[[length(sidebars) + 1]] <- list(
        key = key,
        config = page$sidebar
      )
      key
    }
    normalized_pages[[i]] <- list(
      value = value,
      sidebar_key = sidebar_key,
      title = page$title,
      icon = page$icon,
      nav_id = paste0(resolved_id, "-nav-", i),
      panel_id = paste0(resolved_id, "-panel-", i)
    )
  }

  list(
    pages = normalized_pages,
    sidebars = sidebars,
    home_sidebar_key = home_sidebar_key,
    home_sidebar = home_sidebar
  )
}

sidebar_metadata <- function(sidebar) {
  if (is.null(sidebar)) {
    return(list(open = NULL, width = NULL, resizable = NULL))
  }
  list(
    open = sidebar$open,
    width = sidebar$width,
    resizable = if (sidebar$resizable) "true" else "false"
  )
}

page_chat_sidebar_panel <- function(config, key, id, hidden) {
  metadata <- sidebar_metadata(config)
  htmltools::tags$div(
    class = "shiny-chat-page-sidebar-panel",
    `data-sidebar-for` = key,
    `data-sidebar-open` = metadata$open,
    `data-sidebar-width` = metadata$width,
    `data-sidebar-resizable` = metadata$resizable,
    hidden = if (hidden) NA,
    if (config$history) chat_ui_history_tag(id),
    !!!config$content
  )
}

page_chat_identity_content <- function(icon, title) {
  htmltools::tagList(
    if (!is.null(icon)) {
      htmltools::tags$span(class = "shiny-chat-page-identity-icon", icon)
    },
    htmltools::tags$span(class = "shiny-chat-page-identity-title", title)
  )
}

page_chat_nav_control <- function(page) {
  htmltools::tags$button(
    id = page$nav_id,
    type = "button",
    class = "shiny-chat-page-nav-link",
    `aria-controls` = page$panel_id,
    `data-page-target` = page$value,
    if (!is.null(page$icon)) {
      htmltools::tags$span(class = "shiny-chat-page-nav-icon", page$icon)
    },
    htmltools::tags$span(class = "shiny-chat-page-nav-title", page$title)
  )
}

normalize_chat_window_title <- function(window_title, title) {
  if (
    length(window_title) == 1 &&
      is.atomic(window_title) &&
      is.na(window_title)
  ) {
    if (
      rlang::is_string(title) &&
        !inherits(title, "html") &&
        !is.na(title)
    ) {
      return(title)
    }
    return(NULL)
  }
  if (is.null(window_title)) {
    return(NULL)
  }
  chat_validate_plain_string(window_title, "window_title", allow_empty = TRUE)
  window_title
}

chat_validate_plain_string <- function(value, arg, allow_empty = FALSE) {
  if (
    !rlang::is_string(value) ||
      inherits(value, "html") ||
      is.na(value) ||
      (!allow_empty && !nzchar(trimws(value)))
  ) {
    requirement <- if (allow_empty) "a string" else "a non-empty string"
    cli::cli_abort("{.arg {arg}} must be {requirement}.")
  }
  invisible()
}

chat_validate_page_ui <- function(value, arg, allow_null = TRUE) {
  if (is.null(value)) {
    if (allow_null) {
      return(invisible())
    }
    cli::cli_abort("{.arg {arg}} must be text or UI content.")
  }

  is_ui <- function(x) {
    if (is.null(x)) {
      return(TRUE)
    }
    if (
      inherits(
        x,
        c("shiny.tag", "shiny.tag.list", "shiny.tag.function", "html")
      )
    ) {
      return(TRUE)
    }
    if (is.character(x)) {
      return(length(x) == 1 && !anyNA(x))
    }
    if (is.numeric(x)) {
      return(length(x) == 1 && all(is.finite(x)))
    }
    if (is.list(x)) {
      return(all(vapply(x, is_ui, logical(1))))
    }
    FALSE
  }

  if (!is_ui(value)) {
    cli::cli_abort("{.arg {arg}} must be text or UI content.")
  }
  invisible()
}

chat_config_content <- function(...) {
  content <- rlang::list2(...)
  if (any(nzchar(rlang::names2(content)))) {
    rlang::abort("Arguments in ... must be unnamed UI content.")
  }
  content
}

chat_validate_boolean <- function(value, arg) {
  if (!is.logical(value) || length(value) != 1 || is.na(value)) {
    cli::cli_abort("{.arg {arg}} must be {.code TRUE} or {.code FALSE}.")
  }
}

chat_validate_width <- function(value, arg) {
  if (
    length(value) != 1 ||
      is.na(value) ||
      (!is.numeric(value) && !is.character(value)) ||
      (is.numeric(value) && (!is.finite(value) || value <= 0))
  ) {
    cli::cli_abort(
      "{.arg {arg}} must be a positive number or a non-empty CSS length."
    )
  }

  tryCatch(
    htmltools::validateCssUnit(value),
    error = function(cnd) {
      cli::cli_abort(
        "{.arg {arg}} must be a valid CSS length.",
        parent = cnd
      )
    }
  )
}

chat_validate_string <- function(value, arg, allow_empty = FALSE) {
  if (
    !rlang::is_string(value) ||
      is.na(value) ||
      (!allow_empty && !nzchar(value))
  ) {
    requirement <- if (allow_empty) "a string" else "a non-empty string"
    cli::cli_abort("{.arg {arg}} must be {requirement}.")
  }
}

chat_normalize_sidebar_open <- function(open) {
  if (isTRUE(open)) {
    return("open")
  }
  if (isFALSE(open)) {
    return("closed")
  }
  if (
    !rlang::is_string(open) || !open %in% c("auto", "open", "closed", "always")
  ) {
    cli::cli_abort(
      "{.arg open} must be one of {.val auto}, {.val open}, {.val closed}, or {.val always}."
    )
  }
  open
}

chat_validate_sidebar <- function(sidebar) {
  if (
    isTRUE(sidebar) || isFALSE(sidebar) || inherits(sidebar, "chat_sidebar")
  ) {
    return(invisible())
  }
  cli::cli_abort(
    "{.arg sidebar} must be {.code TRUE}, {.code FALSE}, or a {.fn chat_sidebar} configuration."
  )
}

normalize_chat_artifact <- function(artifact) {
  if (isTRUE(artifact)) {
    return(chat_artifact())
  }
  if (isFALSE(artifact)) {
    return(NULL)
  }
  if (inherits(artifact, "chat_artifact")) {
    return(artifact)
  }
  cli::cli_abort(
    "{.arg artifact} must be {.code TRUE}, {.code FALSE}, or a {.fn chat_artifact} configuration."
  )
}

chat_artifact_tag <- function(artifact) {
  htmltools::tag(
    "shiny-chat-artifact",
    rlang::list2(
      title = artifact$title,
      width = artifact$width,
      open = if (artifact$open) NA,
      resizable = if (!artifact$resizable) "false",
      !!!artifact$content,
      htmltools::findDependencies(artifact$content)
    )
  )
}
