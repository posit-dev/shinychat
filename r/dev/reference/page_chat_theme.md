# Create a theme for `page_chat()`

`page_chat_theme()` layers page-scoped surface, chat-radius, and density
tokens and system typography over bslib's `"shiny"` preset. Supply a
different `preset` to start from another bslib or Bootswatch preset, or
pass a regular
[`bslib::bs_theme()`](https://rstudio.github.io/bslib/reference/bs_theme.html)
directly to
[`page_chat()`](https://posit-dev.github.io/shinychat/r/dev/reference/page_chat.md)
to omit the page-chat baseline.

## Usage

``` r
page_chat_theme(..., preset = "shiny")
```

## Arguments

- ...:

  Sass variables forwarded to
  [`bslib::bs_theme()`](https://rstudio.github.io/bslib/reference/bs_theme.html).
  Values supplied here override the page-chat defaults.

- preset:

  A bslib or Bootswatch preset name.

## Value

A
[`bslib::bs_theme()`](https://rstudio.github.io/bslib/reference/bs_theme.html)
suitable for the `theme` argument of
[`page_chat()`](https://posit-dev.github.io/shinychat/r/dev/reference/page_chat.md).
