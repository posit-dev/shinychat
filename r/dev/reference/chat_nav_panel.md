# Create a page-chat navigation panel

Creates a secondary page for
[`page_chat()`](https://posit-dev.github.io/shinychat/r/dev/reference/page_chat.md)
in the same style as
[`bslib::nav_panel()`](https://rstudio.github.io/bslib/reference/nav-items.html)
and
[`bslib::page_navbar()`](https://rstudio.github.io/bslib/reference/page_navbar.html).
When users navigate to the panel, the chat remains mounted on the home
page so its conversation and UI state persist.

## Usage

``` r
chat_nav_panel(
  title,
  ...,
  value = NULL,
  icon = NULL,
  sidebar = FALSE,
  toolbar = NULL,
  content_width = "min(680px, 100%)"
)
```

## Arguments

- title:

  The panel title.

- ...:

  UI content to display when the panel is active.

- value:

  An optional unique navigation value. Defaults to `title`. The value
  `"__home__"` is reserved for the main chat page.

- icon:

  An optional icon to display with the title.

- sidebar:

  Whether to use the default sidebar (`TRUE`), no page-specific sidebar
  (`FALSE`), or a
  [`chat_sidebar()`](https://posit-dev.github.io/shinychat/r/dev/reference/chat_sidebar.md)
  or
  [`bslib::sidebar()`](https://rstudio.github.io/bslib/reference/sidebar.html)
  configuration. A
  [`chat_sidebar()`](https://posit-dev.github.io/shinychat/r/dev/reference/chat_sidebar.md)
  with `history = NULL` defaults to `FALSE` here.

- toolbar:

  `NULL` (the default) for no page-scoped toolbar, or UI content for a
  page-specific toolbar. Use
  [`bslib::toolbar()`](https://rstudio.github.io/bslib/reference/toolbar.html)
  to group toolbar controls.

- content_width:

  Maximum panel-content width. Content is centered and receives
  responsive inline padding. Use exactly `"100%"`, `"100vw"`, or
  `"100dvw"` for full-bleed content without component-provided padding.

## Value

A configuration object for use with
[`page_chat()`](https://posit-dev.github.io/shinychat/r/dev/reference/page_chat.md).
