# Create a full-window chat page

`page_chat()` creates a fillable page containing one persistent
[`chat_ui()`](https://posit-dev.github.io/shinychat/r/dev/reference/chat_ui.md)
home view, optional navigation pages, and a responsive app-menu sidebar.

Use `page_chat()` as the top-level page UI when the chat owns the full
browser window. It owns the page layout, the single mounted chat, and
the responsive app-menu controls. Use
[`chat_ui()`](https://posit-dev.github.io/shinychat/r/dev/reference/chat_ui.md)
directly when the chat is embedded in an existing layout or alongside
other top-level page content. For a standalone interactive chat
application, use
[`chat_app()`](https://posit-dev.github.io/shinychat/r/dev/reference/chat_app.md),
which composes `page_chat()` with
[`chat_server()`](https://posit-dev.github.io/shinychat/r/dev/reference/chat_app.md).

## Usage

``` r
page_chat(
  title,
  icon = NULL,
  ...,
  id = "chat",
  pages_navbar = NULL,
  toolbar = NULL,
  toolbar_global = bslib::toolbar(bslib::input_dark_mode()),
  toolbar_input = NULL,
  navbar_options = NULL,
  sidebar = TRUE,
  messages = NULL,
  greeting = NULL,
  placeholder = "Enter a message...",
  width = "min(680px, 100%)",
  icon_assistant = NULL,
  icon_send = NULL,
  enable_cancel = NULL,
  allow_attachments = NULL,
  footer = NULL,
  drawer = TRUE,
  window_title = NA,
  lang = NULL,
  theme = page_chat_theme()
)
```

## Arguments

- title:

  The display title. May be text or reactive/static UI.

- icon:

  Optional UI displayed before `title`.

- ...:

  Named lower-frequency
  [`chat_ui()`](https://posit-dev.github.io/shinychat/r/dev/reference/chat_ui.md)
  arguments and HTML attributes. `page_chat()` owns `height`, `fill`,
  and `show_history`; attempts to pass those arguments are rejected.

- id:

  A non-empty string identifying the chat. The currently selected page
  is readable server-side as `input$<id>_page` and settable via
  [`bslib::nav_select()`](https://rstudio.github.io/bslib/reference/nav_select.html).
  Use
  [`bslib::nav_show()`](https://rstudio.github.io/bslib/reference/nav_select.html)
  and
  [`bslib::nav_hide()`](https://rstudio.github.io/bslib/reference/nav_select.html)
  to reveal or hide nav controls. The reserved value `"__home__"`
  represents the main chat page.

- pages_navbar:

  `NULL` or a list of
  [`chat_nav_panel()`](https://posit-dev.github.io/shinychat/r/dev/reference/chat_nav_panel.md)
  configurations and supported standard bslib navigation items. Standard
  content panels use the normal page-chat content width with no
  page-specific sidebar or toolbar.
  [`bslib::nav_panel_hidden()`](https://rstudio.github.io/bslib/reference/nav-items.html)
  panels render their nav control hidden; use
  [`bslib::nav_show()`](https://rstudio.github.io/bslib/reference/nav_select.html)
  to reveal it.

- toolbar:

  Optional home-page-scoped UI displayed with the navigation controls.
  Use
  [`bslib::toolbar()`](https://rstudio.github.io/bslib/reference/toolbar.html)
  to group toolbar controls. A panel's `chat_nav_panel(toolbar = )`
  replaces this scoped segment.

- toolbar_global:

  Optional persistent UI displayed after the page-scoped toolbar in the
  navigation controls. Use
  [`bslib::toolbar()`](https://rstudio.github.io/bslib/reference/toolbar.html)
  to group toolbar controls. Defaults to a toolbar containing
  [`bslib::input_dark_mode()`](https://rstudio.github.io/bslib/reference/input_dark_mode.html);
  use `NULL` to opt out. It remains mounted while secondary pages are
  selected and while controls move between desktop and mobile layouts.

- toolbar_input:

  Optional UI displayed directly below the chat input. Use
  [`bslib::toolbar()`](https://rstudio.github.io/bslib/reference/toolbar.html)
  to group toolbar controls. This is independent of the navigation
  `toolbar`.

- navbar_options:

  Optional
  [`bslib::navbar_options()`](https://rstudio.github.io/bslib/reference/navbar_options.html)
  that styles the page title bar. Its `bg`, `theme`, `underline`, and
  HTML attributes are supported. `position` and `collapsible` are
  unsupported because `page_chat()` owns the full-window layout and
  responsive app menu.

- sidebar:

  Whether to use the default history sidebar (`TRUE`), omit the default
  sidebar (`FALSE`), or use a
  [`chat_sidebar()`](https://posit-dev.github.io/shinychat/r/dev/reference/chat_sidebar.md)
  or
  [`bslib::sidebar()`](https://rstudio.github.io/bslib/reference/sidebar.html)
  configuration. A bslib sidebar supplies its child content, width,
  initial open state, and resizability; its history defaults to `FALSE`.
  A
  [`chat_sidebar()`](https://posit-dev.github.io/shinychat/r/dev/reference/chat_sidebar.md)
  with `history = NULL` defaults to `TRUE` here.

- messages, greeting, placeholder, width, icon_assistant, icon_send,
  enable_cancel, allow_attachments, footer, drawer:

  Common arguments passed to
  [`chat_ui()`](https://posit-dev.github.io/shinychat/r/dev/reference/chat_ui.md).

- window_title:

  A static browser-window title. The default, `NA`, derives the window
  title from `title` when `title` is a scalar string. Use `NULL` to omit
  the window title.

- lang:

  An optional non-empty document language string.

- theme:

  A
  [`bslib::bs_theme()`](https://rstudio.github.io/bslib/reference/bs_theme.html)
  object. Defaults to
  [`page_chat_theme()`](https://posit-dev.github.io/shinychat/r/dev/reference/page_chat_theme.md).
  Supply
  [`bslib::bs_theme()`](https://rstudio.github.io/bslib/reference/bs_theme.html)
  directly to use another bslib preset or a completely custom Bootstrap
  theme.

## Value

A fillable bslib page.

## Migration from [`page_fillable()`](https://rstudio.github.io/bslib/reference/page_fillable.html)

Replace:

    bslib::page_fillable(chat_ui("chat", fill = TRUE))

with:

    page_chat("Assistant", id = "chat")

The page supplies the full-window sizing and keeps `show_history = TRUE`
on the mounted chat. Do not wrap `page_chat()` in another page container
or pass `height`, `fill`, or `show_history`; those arguments are
page-owned.

## Navigation, sidebars, and artifacts

`pages_navbar` accepts a list of additional navbar items. Use
[`chat_nav_panel()`](https://posit-dev.github.io/shinychat/r/dev/reference/chat_nav_panel.md)
when a page needs page-chat-specific sidebar, toolbar, or content-width
options. It also accepts
[`bslib::nav_panel()`](https://rstudio.github.io/bslib/reference/nav-items.html),
[`bslib::nav_panel_hidden()`](https://rstudio.github.io/bslib/reference/nav-items.html),
[`bslib::nav_menu()`](https://rstudio.github.io/bslib/reference/nav-items.html),
[`bslib::nav_item()`](https://rstudio.github.io/bslib/reference/nav-items.html),
and
[`bslib::nav_spacer()`](https://rstudio.github.io/bslib/reference/nav-items.html).
Programmatic navigation uses standard bslib helpers against the derived
`"<id>_page"` id:
[`bslib::nav_select()`](https://rstudio.github.io/bslib/reference/nav_select.html)
to switch pages (including hidden panels and
[`nav_menu()`](https://rstudio.github.io/bslib/reference/nav-items.html)
children),
[`bslib::nav_show()`](https://rstudio.github.io/bslib/reference/nav_select.html)
and
[`bslib::nav_hide()`](https://rstudio.github.io/bslib/reference/nav_select.html)
to reveal or hide nav controls. The active page is readable as
`input$<id>_page` (`"__home__"` when the main chat page is active).
Sidebar navigation is not yet implemented. Each panel can use the
default sidebar, no page-specific sidebar, or its own
[`chat_sidebar()`](https://posit-dev.github.io/shinychat/r/dev/reference/chat_sidebar.md)
or
[`bslib::sidebar()`](https://rstudio.github.io/bslib/reference/sidebar.html)
configuration. The `sidebar` argument configures the home view. Use
[`bslib::toolbar()`](https://rstudio.github.io/bslib/reference/toolbar.html)
to group controls in `toolbar`; it is a home-page-scoped segment
rendered with the page navigation controls and follows them into the
mobile app menu. A panel's `toolbar = NULL` omits that scoped segment;
`chat_nav_panel(toolbar = bslib::toolbar(...))` supplies a page-specific
replacement. Use `toolbar_global = bslib::toolbar(...)` for a persistent
segment that remains mounted on every page after the active scoped
toolbar. On narrow screens, navigation and toolbar controls move into
the app menu above the active page's sidebar content without duplicating
Shiny input or output IDs. By default, `toolbar_global` contains
[`bslib::input_dark_mode()`](https://rstudio.github.io/bslib/reference/input_dark_mode.html);
use `NULL` to opt out.

Set `drawer` to a
[`chat_drawer()`](https://posit-dev.github.io/shinychat/r/dev/reference/chat_drawer.md)
configuration to provide initial content and layout options. Update the
mounted drawer from the server with
[`chat_drawer_show()`](https://posit-dev.github.io/shinychat/r/dev/reference/chat_drawer_show.md),
[`chat_drawer_update()`](https://posit-dev.github.io/shinychat/r/dev/reference/chat_drawer_update.md),
[`chat_drawer_hide()`](https://posit-dev.github.io/shinychat/r/dev/reference/chat_drawer_hide.md),
and
[`chat_drawer_toggle()`](https://posit-dev.github.io/shinychat/r/dev/reference/chat_drawer_toggle.md).
Artifact content is static UI passed through those server functions; use
ordinary Shiny inputs and outputs inside that content when needed. You
can try navigation and artifact-control examples, which do not require
credentials, through
`shiny::runExample("page-chat-navigation", package = "shinychat")` and
`shiny::runExample("page-chat-drawer-controls", package = "shinychat")`.

`page_chat()` owns page composition and accepts one chat root. Do not
pass unrelated top-level UI or a second chat root. Existing apps that
need those layouts should continue using
[`chat_ui()`](https://posit-dev.github.io/shinychat/r/dev/reference/chat_ui.md)
with
[`bslib::page_fillable()`](https://rstudio.github.io/bslib/reference/page_fillable.html),
[`bslib::page_sidebar()`](https://rstudio.github.io/bslib/reference/page_sidebar.html),
or another appropriate container.

## Examples

``` r
if (FALSE) { # interactive()
library(shiny)
library(shinychat)

artifact_content <- function(label) {
  tags$div(
    tags$h3("Preview"),
    tags$p(label)
  )
}

ui <- page_chat(
  "Assistant",
  messages = "Welcome! Ask a question to get started.",
  toolbar = bslib::toolbar(actionButton("show_preview", "Show preview")),
  toolbar_global = actionButton("help", "Help"),
  sidebar = chat_sidebar(
    tags$p("Home tools"),
    history = FALSE,
    open = "open"
  ),
  pages_navbar = list(
    chat_nav_panel(
      "About",
      tags$p("This is a secondary page."),
      value = "about",
    ),
    chat_nav_panel(
      "Settings",
      tags$p("Settings live here."),
      value = "settings",
      sidebar = chat_sidebar(
        tags$p("Settings menu"),
        width = 320,
        open = "closed"
      ),
      toolbar = bslib::toolbar(actionButton("save_settings", "Save settings"))
    )
  ),
  drawer = chat_drawer(
    artifact_content("Initial preview"),
    title = "Preview"
  )
)

server <- function(input, output, session) {
  observeEvent(input$chat_user_input, {
    chat_append("chat", paste0("You said: ", input$chat_user_input))
  })

  observeEvent(input$show_preview, {
    chat_drawer_show(
      "chat",
      content = artifact_content("Preview opened from the server"),
      title = "Preview"
    )
  })
}

shinyApp(ui, server)
}
```
