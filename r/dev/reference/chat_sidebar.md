# Create a chat sidebar configuration

Configures sidebar content for the home view or a
[`chat_nav_panel()`](https://posit-dev.github.io/shinychat/r/dev/reference/chat_nav_panel.md)
in
[`page_chat()`](https://posit-dev.github.io/shinychat/r/dev/reference/page_chat.md).
A page-chat sidebar behaves like a compact
[`bslib::sidebar()`](https://rstudio.github.io/bslib/reference/sidebar.html)
beside the chat and can include the chat's conversation history
selector.

## Usage

``` r
chat_sidebar(..., history = NULL, width = 280, open = "auto", resizable = TRUE)
```

## Arguments

- ...:

  UI content to display in the sidebar.

- history:

  Whether to display the chat history selector in the sidebar. When
  `NULL`,
  [`page_chat()`](https://posit-dev.github.io/shinychat/r/dev/reference/page_chat.md)
  defaults to `TRUE` and
  [`chat_nav_panel()`](https://posit-dev.github.io/shinychat/r/dev/reference/chat_nav_panel.md)
  defaults to `FALSE`.

- width:

  The initial sidebar width. Positive numbers are converted to pixels;
  character values must be valid CSS lengths.

- open:

  The initial sidebar state. One of `"auto"`, `"open"`, `"closed"`, or
  `"always"`. Logical values are aliases for `"open"` and `"closed"`.

- resizable:

  Whether the sidebar can be resized on desktop.

## Value

A configuration object for use with
[`page_chat()`](https://posit-dev.github.io/shinychat/r/dev/reference/page_chat.md)
or
[`chat_nav_panel()`](https://posit-dev.github.io/shinychat/r/dev/reference/chat_nav_panel.md).

## Examples

``` r
ui <- page_chat(
  "Assistant",
  sidebar = chat_sidebar(
    shiny::tags$p("Workspace"),
    history = TRUE,
    open = "open"
  )
)
```
