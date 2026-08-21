#' Create a full-window chat page
#'
#' @description
#' `page_chat()` creates a fillable page containing one persistent [chat_ui()]
#' home view, optional navigation pages, and a responsive app-menu sidebar.
#'
#' Use `page_chat()` as the top-level page UI when the chat owns the full
#' browser window. It owns the page layout, the single mounted chat, and the
#' responsive app-menu controls. Use [chat_ui()] directly when the chat is
#' embedded in an existing layout or alongside other top-level page content.
#' For a standalone interactive chat application, use [chat_app()], which
#' composes `page_chat()` with [chat_server()].
#'
#' @section Migration from `page_fillable()`:
#'
#' Replace:
#'
#' ```
#' bslib::page_fillable(chat_ui("chat", fill = TRUE))
#' ```
#'
#' with:
#'
#' ```
#' page_chat("Assistant", id = "chat")
#' ```
#'
#' The page supplies the full-window sizing and keeps `show_history = TRUE`
#' on the mounted chat. Do not wrap `page_chat()` in another page container or pass
#' `height`, `fill`, or `show_history`; those arguments are page-owned.
#'
#' @section Navigation, sidebars, and artifacts:
#'
#' `pages` accepts a list of additional pages, each created with
#' [chat_nav_panel()].
#' Each panel can use the default sidebar, no page-specific sidebar, or its
#' own [chat_sidebar()] or [bslib::sidebar()] configuration. The `sidebar`
#' argument configures the
#' home view; `toolbar` is a home-page-scoped segment rendered with the page
#' navigation controls and follows them into the mobile app menu.
#' `toolbar_global` is a persistent segment that remains mounted on every page.
#' A panel's `toolbar = NULL` omits the home-scoped segment; custom UI replaces
#' it. On narrow screens, navigation and toolbar controls move into the app
#' menu above the active page's sidebar content without duplicating Shiny input
#' or output IDs.
#'
#' Set `artifact` to a [chat_artifact()] configuration to provide initial
#' content and layout options. Update the mounted artifact from the server
#' with [chat_artifact_show()], [chat_artifact_update()],
#' [chat_artifact_hide()], and [chat_artifact_toggle()]. Artifact content is
#' static UI passed through those server functions; use ordinary Shiny
#' inputs and outputs inside that content when needed.
#' You can try navigation and artifact-control examples, which do not require
#' credentials, through
#' `shiny::runExample("page-chat-navigation", package = "shinychat")` and
#' `shiny::runExample("page-chat-artifact-controls", package = "shinychat")`.
#'
#' `page_chat()` owns page composition and accepts one chat root. Do not pass
#' unrelated top-level UI or a second chat root. Existing apps that need those
#' layouts should continue using [chat_ui()] with [bslib::page_fillable()],
#' [bslib::page_sidebar()], or another appropriate container.
#'
#' @param title The display title. May be text or reactive/static UI.
#' @param icon Optional UI displayed before `title`.
#' @param ... Named lower-frequency [chat_ui()] arguments and HTML attributes.
#'   `page_chat()` owns `height`, `fill`, and `show_history`; attempts to pass
#'   those arguments are rejected.
#' @param id A non-empty string identifying the chat.
#' @param pages `NULL` or a list of [chat_nav_panel()] configurations.
#' @param toolbar Optional home-page-scoped UI displayed with the navigation
#'   controls. A panel's `chat_nav_panel(toolbar = )` can replace this segment.
#' @param toolbar_global Optional persistent UI displayed after the page-scoped
#'   toolbar in the navigation controls. Defaults to a toolbar containing
#'   [bslib::input_dark_mode()]; use `NULL` to opt out.
#' @param navbar_options Optional [bslib::navbar_options()] that styles the
#'   page title bar. Its `bg`, `theme`, `underline`, and HTML attributes are
#'   supported. `position` and `collapsible` are unsupported because
#'   `page_chat()` owns the full-window layout and responsive app menu.
#' @param sidebar Whether to use the default history sidebar (`TRUE`), omit the
#'   default sidebar (`FALSE`), or use a
#'   [chat_sidebar()] or [bslib::sidebar()] configuration. A bslib sidebar
#'   supplies its child content, width, initial open state, and resizability;
#'   its history defaults to `FALSE`. A [chat_sidebar()] with `history = NULL`
#'   defaults to `TRUE` here.
#' @param messages,greeting,placeholder,width,icon_assistant,enable_cancel,allow_attachments,footer,artifact
#'   Common arguments passed to [chat_ui()].
#' @param window_title A static browser-window title. The default, `NA`,
#'   derives the window title from `title` when `title` is a scalar string.
#'   Use `NULL` to omit the window title.
#' @param lang An optional non-empty document language string.
#' @param theme A [bslib::bs_theme()] object. Defaults to [page_chat_theme()].
#'   Supply [bslib::bs_theme()] directly to use another bslib preset or a
#'   completely custom Bootstrap theme.
#'
#' @returns A fillable bslib page.
#'
#' @examplesIf interactive()
#' library(shiny)
#' library(shinychat)
#'
#' artifact_content <- function(label) {
#'   tags$div(
#'     tags$h3("Preview"),
#'     tags$p(label)
#'   )
#' }
#'
#' ui <- page_chat(
#'   "Assistant",
#'   messages = "Welcome! Ask a question to get started.",
#'   toolbar = actionButton("show_preview", "Show preview"),
#'   toolbar_global = actionButton("help", "Help"),
#'   sidebar = chat_sidebar(
#'     tags$p("Home tools"),
#'     history = FALSE,
#'     open = "open"
#'   ),
#'   pages = list(
#'     chat_nav_panel(
#'       "About",
#'       tags$p("This is a secondary page."),
#'       value = "about",
#'     ),
#'     chat_nav_panel(
#'       "Settings",
#'       tags$p("Settings live here."),
#'       value = "settings",
#'       sidebar = chat_sidebar(
#'         tags$p("Settings menu"),
#'         width = 320,
#'         open = "closed"
#'       ),
#'       toolbar = actionButton("save_settings", "Save settings")
#'     )
#'   ),
#'   artifact = chat_artifact(
#'     artifact_content("Initial preview"),
#'     title = "Preview"
#'   )
#' )
#'
#' server <- function(input, output, session) {
#'   observeEvent(input$chat_user_input, {
#'     chat_append("chat", paste0("You said: ", input$chat_user_input))
#'   })
#'
#'   observeEvent(input$show_preview, {
#'     chat_artifact_show(
#'       "chat",
#'       content = artifact_content("Preview opened from the server"),
#'       title = "Preview"
#'     )
#'   })
#' }
#'
#' shinyApp(ui, server)
#' @export
page_chat <- function(
  title,
  icon = NULL,
  ...,
  id = "chat",
  pages = NULL,
  toolbar = NULL,
  toolbar_global = bslib::toolbar(bslib::input_dark_mode()),
  navbar_options = NULL,
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
  theme = page_chat_theme()
) {
  dots <- rlang::dots_list(...)
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
      i = "Remove {cli::qty(owned_args)}the supplied argument{?s}; the page always uses {.code height = \"100%\"}, {.code fill = TRUE}, and {.code show_history = TRUE}."
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
  chat_validate_page_ui(toolbar_global, "toolbar_global")
  navbar_options <- normalize_page_chat_navbar_options(navbar_options)
  chat_validate_sidebar(sidebar)
  sidebar <- normalize_page_sidebar(sidebar, default_history = TRUE)
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
    show_history = TRUE
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
      htmltools::tags$div(class = "shiny-chat-page-toolbar-scoped"),
      htmltools::tags$div(
        class = "shiny-chat-page-toolbar-global",
        toolbar_global
      )
    )
  )
  toolbar_sources <- htmltools::tags$div(
    class = "shiny-chat-page-toolbar-sources",
    hidden = NA,
    page_chat_toolbar_source("home", toolbar),
    lapply(
      normalized$pages,
      function(page) {
        if (is.null(page$toolbar_key) || identical(page$toolbar_key, "home")) {
          return(NULL)
        }
        page_chat_toolbar_source(page$toolbar_key, page$toolbar)
      }
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
      panel_full_width <- panel$content_width %in% c("100%", "100vw", "100dvw")
      htmltools::tags$section(
        class = "shiny-chat-page-panel",
        id = normalized$panel_id,
        `aria-labelledby` = normalized$nav_id,
        `data-page-value` = normalized$value,
        `data-page-title` = panel$title,
        `data-sidebar-key` = normalized$sidebar_key,
        `data-page-toolbar-source` = normalized$toolbar_key,
        hidden = NA,
        htmltools::tags$div(
          class = "shiny-chat-page-panel-content",
          style = bslib::css(
            "--shiny-chat-page-content-width" = panel$content_width
          ),
          `data-content-full-bleed` = if (panel_full_width) "true",
          !!!panel$content
        )
      )
    },
    pages,
    normalized$pages
  )

  header <- htmltools::tags$header(
    class = "shiny-chat-page-header",
    htmltools::tags$button(
      type = "button",
      class = "shiny-chat-page-sidebar-toggle",
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
      page_chat_sidebar_toggle_icon()
    ),
    identity,
    htmltools::tags$div(
      class = paste(
        "shiny-chat-page-controls-mount",
        "shiny-chat-page-controls-mount-desktop"
      ),
      controls
    )
  )
  header <- apply_page_chat_navbar_options(header, navbar_options)

  root <- htmltools::tag(
    "shiny-chat-page",
    list(
      `data-chat-id` = resolved_id,
      `data-active-page` = "home",
      header,
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
          page_chat_sidebar_close_button(resolved_id),
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
            `data-page-toolbar-source` = "home",
            chat
          ),
          nav_sections
        )
      ),
      toolbar_sources
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

#' Create a chat sidebar configuration
#'
#' @description
#' Configures sidebar content for the home view or a [chat_nav_panel()] in
#' [page_chat()]. A page-chat sidebar behaves like a compact
#' [bslib::sidebar()] beside the chat and can include the chat's conversation
#' history selector.
#'
#' @param ... UI content to display in the sidebar.
#' @param history Whether to display the chat history selector in the sidebar.
#'   When `NULL`, [page_chat()] defaults to `TRUE` and [chat_nav_panel()]
#'   defaults to `FALSE`.
#' @param width The initial sidebar width. Positive numbers are converted to
#'   pixels; character values must be valid CSS lengths.
#' @param open The initial sidebar state. One of `"auto"`, `"open"`, `"closed"`,
#'   or `"always"`. Logical values are aliases for `"open"` and `"closed"`.
#' @param resizable Whether the sidebar can be resized on desktop.
#'
#' @returns A configuration object for use with [page_chat()] or
#'   [chat_nav_panel()].
#'
#' @examples
#' ui <- page_chat(
#'   "Assistant",
#'   sidebar = chat_sidebar(
#'     shiny::tags$p("Workspace"),
#'     history = TRUE,
#'     open = "open"
#'   )
#' )
#' @export
chat_sidebar <- function(
  ...,
  history = NULL,
  width = 280,
  open = "auto",
  resizable = TRUE
) {
  content <- chat_config_content(...)
  if (!is.null(history)) {
    chat_validate_boolean(history, "history")
  }
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

#' Create a page-chat navigation panel
#'
#' @description
#' Creates a secondary page for [page_chat()] in the same style as
#' [bslib::nav_panel()] and [bslib::page_navbar()]. When users navigate to the
#' panel, the chat remains mounted on the home page so its conversation and UI
#' state persist.
#'
#' @param title The panel title.
#' @param ... UI content to display when the panel is active.
#' @param value An optional unique navigation value.
#' @param icon An optional icon to display with the title.
#' @param sidebar Whether to use the default sidebar (`TRUE`), no
#'   page-specific sidebar (`FALSE`), or a
#'   [chat_sidebar()] or [bslib::sidebar()] configuration. A [chat_sidebar()]
#'   with `history = NULL` defaults to `FALSE` here.
#' @param toolbar `NULL` (the default) for no page-scoped toolbar, or UI
#'   content for a page-specific toolbar.
#' @param content_width Maximum panel-content width. Content is centered and
#'   receives responsive inline padding. Use exactly `"100%"`, `"100vw"`, or
#'   `"100dvw"` for full-bleed content without component-provided padding.
#'
#' @returns A configuration object for use with [page_chat()].
#' @export
chat_nav_panel <- function(
  title,
  ...,
  value = NULL,
  icon = NULL,
  sidebar = FALSE,
  toolbar = NULL,
  content_width = "min(680px, 100%)"
) {
  chat_validate_string(title, "title")
  content <- chat_config_content(...)
  if (!is.null(value)) {
    chat_validate_string(value, "value")
  }
  chat_validate_sidebar(sidebar)
  chat_validate_panel_toolbar(toolbar)
  content_width <- chat_validate_content_width(content_width, "content_width")

  structure(
    list(
      title = title,
      content = content,
      value = value,
      icon = icon,
      sidebar = sidebar,
      toolbar = toolbar,
      content_width = content_width
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
  attrs <- rlang::dots_list(...)
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

page_chat_sidebar_close_button <- function(id) {
  bslib::toolbar(
    bslib::toolbar_input_button(
      id = paste0(id, "-sidebar-close"),
      label = "Close app menu",
      icon = htmltools::HTML(
        '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="currentColor" class="bi bi-x" viewBox="0 0 16 16"><path d="M4.646 4.646a.5.5 0 0 1 .708 0L8 7.293l2.646-2.647a.5.5 0 0 1 .708.708L8.707 8l2.647 2.646a.5.5 0 0 1-.708.708L8 8.707l-2.646 2.647a.5.5 0 0 1-.708-.708L7.293 8 4.646 5.354a.5.5 0 0 1 0-.708"/></svg>'
      ),
      class = "shiny-chat-page-sidebar-close"
    )
  )
}

page_chat_sidebar_toggle_icon <- function() {
  htmltools::HTML(
    '<svg class="shiny-chat-page-sidebar-icon bi bi-list" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" aria-hidden="true" focusable="false"><path d="M2.5 12a.5.5 0 0 1 .5-.5h10a.5.5 0 0 1 0 1H3a.5.5 0 0 1-.5-.5m0-4a.5.5 0 0 1 .5-.5h10a.5.5 0 0 1 0 1H3a.5.5 0 0 1-.5-.5m0-4a.5.5 0 0 1 .5-.5h10a.5.5 0 0 1 0 1H3a.5.5 0 0 1-.5-.5"/></svg>'
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
    chat_validate_panel_toolbar(page$toolbar)
    pages[[i]]$content_width <- chat_validate_content_width(
      page$content_width,
      paste0("pages[[", i, "]]$content_width")
    )
    pages[[i]]$sidebar <- normalize_page_sidebar(
      page$sidebar,
      default_history = FALSE
    )
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

normalize_chat_sidebar_config <- function(sidebar, default_history) {
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

  chat_sidebar(
    !!!sidebar$content,
    history = sidebar$history %||% default_history,
    width = sidebar$width,
    open = sidebar$open,
    resizable = sidebar$resizable
  )
}

normalize_bslib_sidebar_config <- function(sidebar) {
  if (identical(sidebar$position, "right")) {
    cli::cli_abort(
      "{.fn page_chat} only supports left-positioned {.fn bslib::sidebar} configurations."
    )
  }

  chat_sidebar(
    !!!sidebar$children,
    history = FALSE,
    width = sidebar$width,
    open = sidebar$open$desktop %||% "auto",
    resizable = sidebar$resizable
  )
}

normalize_page_sidebar <- function(sidebar, default_history) {
  if (inherits(sidebar, "chat_sidebar")) {
    return(normalize_chat_sidebar_config(sidebar, default_history))
  }
  if (inherits(sidebar, "bslib_sidebar")) {
    return(normalize_bslib_sidebar_config(sidebar))
  }
  sidebar
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
      toolbar = page$toolbar,
      toolbar_key = if (is.null(page$toolbar)) {
        NULL
      } else {
        paste0("page-", i)
      },
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

page_chat_toolbar_source <- function(key, content) {
  htmltools::tags$div(
    class = "shiny-chat-page-toolbar-source",
    `data-page-toolbar-source` = key,
    htmltools::tags$div(
      class = "shiny-chat-page-toolbar-content",
      content
    )
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

normalize_page_chat_navbar_options <- function(options) {
  if (is.null(options)) {
    return(bslib::navbar_options())
  }
  if (!inherits(options, "bslib_navbar_options")) {
    cli::cli_abort(
      "{.arg navbar_options} must be created by {.fn bslib::navbar_options}."
    )
  }

  is_default <- attr(options, "is_default")
  unsupported <- c("position", "collapsible")
  supplied <- unsupported[
    !vapply(
      unsupported,
      function(name) isTRUE(is_default[[name]]),
      logical(1)
    )
  ]
  if (length(supplied) > 0) {
    cli::cli_abort(c(
      "{.arg navbar_options} cannot set {.field {supplied}} in {.fn page_chat}.",
      i = "{.fn page_chat} owns the full-window layout and responsive app menu."
    ))
  }

  options
}

apply_page_chat_navbar_options <- function(header, options) {
  attrs <- options$attribs %||% list()
  if (length(attrs) > 0) {
    header <- rlang::exec(htmltools::tagAppendAttributes, header, !!!attrs)
  }
  header <- htmltools::tagAppendAttributes(
    header,
    `data-bs-theme` = options$theme,
    `data-shiny-chat-page-nav-style` = if (isTRUE(options$underline)) {
      "underline"
    } else {
      "pill"
    }
  )
  if (!is.null(options$bg)) {
    header <- htmltools::tagAppendAttributes(
      header,
      style = paste0("background-color:", options$bg, ";")
    )
  }

  header
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
  if (inherits(value, "html")) {
    cli::cli_abort("{.arg {arg}} must be a plain string.")
  }
  rlang::check_string(
    value,
    allow_empty = allow_empty,
    allow_na = FALSE,
    arg = arg
  )
  if (!allow_empty && !nzchar(trimws(value))) {
    cli::cli_abort("{.arg {arg}} must not be blank.")
  }
  invisible()
}

chat_validate_page_ui <- function(value, arg, allow_null = TRUE) {
  if (!is.null(value)) {
    return(invisible())
  }
  if (allow_null) {
    return(invisible())
  }
  cli::cli_abort("{.arg {arg}} must not be NULL.")
  invisible()
}

chat_validate_panel_toolbar <- function(value) {
  if (is.null(value)) {
    return(invisible())
  }
  if (is.logical(value)) {
    cli::cli_abort("{.arg toolbar} must be NULL or UI content.")
  } else {
    chat_validate_page_ui(value, "toolbar", allow_null = FALSE)
  }
  invisible()
}

chat_config_content <- function(...) {
  content <- rlang::dots_list(...)
  if (any(nzchar(rlang::names2(content)))) {
    rlang::abort("Arguments in ... must be unnamed UI content.")
  }
  unname(content)
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

chat_validate_content_width <- function(value, arg) {
  if (
    length(value) != 1 ||
      is.na(value) ||
      (!is.numeric(value) && !is.character(value)) ||
      (is.numeric(value) && (!is.finite(value) || value <= 0)) ||
      (is.character(value) && !nzchar(trimws(value)))
  ) {
    cli::cli_abort(
      "{.arg {arg}} must be a positive number or a non-empty CSS width."
    )
  }

  if (is.numeric(value)) {
    return(htmltools::validateCssUnit(value))
  }

  # CSS functions and custom properties are valid page content widths even
  # though htmltools::validateCssUnit() only accepts simple CSS units.
  value
}

chat_validate_string <- function(value, arg, allow_empty = FALSE) {
  rlang::check_string(
    value,
    allow_empty = allow_empty,
    allow_na = FALSE,
    arg = arg
  )
  invisible()
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
    isTRUE(sidebar) ||
      isFALSE(sidebar) ||
      inherits(sidebar, "chat_sidebar") ||
      inherits(sidebar, "bslib_sidebar")
  ) {
    return(invisible())
  }
  cli::cli_abort(
    "{.arg sidebar} must be {.code TRUE}, {.code FALSE}, or a {.fn chat_sidebar} or {.fn bslib::sidebar} configuration."
  )
}

normalize_chat_artifact <- function(artifact) {
  if (isTRUE(artifact)) {
    return(chat_artifact(open = FALSE))
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
