# Toggle a chat drawer

Toggle a chat drawer

## Usage

``` r
chat_drawer_toggle(id, session = shiny::getDefaultReactiveDomain())
```

## Arguments

- id:

  The ID of the chat element.

- session:

  The Shiny session object.

## Value

Invisibly, `NULL`.

## See also

[`chat_drawer()`](https://posit-dev.github.io/shinychat/r/dev/reference/chat_drawer.md)
to configure a drawer, and
[`chat_ui()`](https://posit-dev.github.io/shinychat/r/dev/reference/chat_ui.md)
or
[`page_chat()`](https://posit-dev.github.io/shinychat/r/dev/reference/page_chat.md)
to display one.

Other chat drawers:
[`chat_drawer()`](https://posit-dev.github.io/shinychat/r/dev/reference/chat_drawer.md),
[`chat_drawer_hide()`](https://posit-dev.github.io/shinychat/r/dev/reference/chat_drawer_hide.md),
[`chat_drawer_show()`](https://posit-dev.github.io/shinychat/r/dev/reference/chat_drawer_show.md),
[`chat_drawer_update()`](https://posit-dev.github.io/shinychat/r/dev/reference/chat_drawer_update.md)
