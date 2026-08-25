# Create a chat drawer configuration

An drawer displays UI content adjacent to a chat interface, such as a
preview, a generated report, or a detail view. Use `chat_drawer()` to
supply its initial content and layout to the `drawer` argument of
[`chat_ui()`](https://posit-dev.github.io/shinychat/r/dev/reference/chat_ui.md)
or
[`page_chat()`](https://posit-dev.github.io/shinychat/r/dev/reference/page_chat.md).
Update the panel later with the other drawer functions.

## Usage

``` r
chat_drawer(..., title = NULL, width = 400, open = TRUE, resizable = TRUE)
```

## Arguments

- ...:

  UI content to display in the drawer.

- title:

  An optional drawer title.

- width:

  The initial drawer width. Positive numbers are converted to pixels;
  character values must be valid CSS lengths.

- open:

  Whether the drawer is initially visible.

- resizable:

  Whether the drawer can be resized on desktop.

## Value

A configuration object for use with
[`chat_ui()`](https://posit-dev.github.io/shinychat/r/dev/reference/chat_ui.md)
or
[`page_chat()`](https://posit-dev.github.io/shinychat/r/dev/reference/page_chat.md).

## See also

[`chat_ui()`](https://posit-dev.github.io/shinychat/r/dev/reference/chat_ui.md)
and
[`page_chat()`](https://posit-dev.github.io/shinychat/r/dev/reference/page_chat.md)
accept this configuration through their `drawer` argument.

Other chat drawers:
[`chat_drawer_hide()`](https://posit-dev.github.io/shinychat/r/dev/reference/chat_drawer_hide.md),
[`chat_drawer_show()`](https://posit-dev.github.io/shinychat/r/dev/reference/chat_drawer_show.md),
[`chat_drawer_toggle()`](https://posit-dev.github.io/shinychat/r/dev/reference/chat_drawer_toggle.md),
[`chat_drawer_update()`](https://posit-dev.github.io/shinychat/r/dev/reference/chat_drawer_update.md)
