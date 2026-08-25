# Update a chat drawer

Updates a chat's drawer content or title without changing its
visibility. Omitted fields preserve their current value. Use an empty
[`htmltools::tagList()`](https://rstudio.github.io/htmltools/reference/tagList.html)
to clear content or `""` to clear the title.

## Usage

``` r
chat_drawer_update(
  id,
  content = NULL,
  title = NULL,
  session = shiny::getDefaultReactiveDomain()
)
```

## Arguments

- id:

  The ID of the chat element.

- content:

  Optional UI content for the drawer.

- title:

  Optional drawer title.

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
[`chat_drawer_toggle()`](https://posit-dev.github.io/shinychat/r/dev/reference/chat_drawer_toggle.md)
