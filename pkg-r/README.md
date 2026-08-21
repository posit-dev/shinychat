# shinychat <a href="https://posit-dev.github.io/shinychat/r/"><img src="man/figures/logo.svg" align="right" height="138" alt="shinychat for R website" /></a>

<!-- badges: start -->
[![R-CMD-check](https://github.com/posit-dev/shinychat/actions/workflows/R-CMD-check.yaml/badge.svg)](https://github.com/posit-dev/shinychat/actions/workflows/R-CMD-check.yaml)
[![CRAN status](https://www.r-pkg.org/badges/version/shinychat)](https://CRAN.R-project.org/package=shinychat)
[![shinychat status badge](https://posit-dev.r-universe.dev/shinychat/badges/version)](https://posit-dev.r-universe.dev/shinychat)
<!-- badges: end -->

**shinychat** provides a [Shiny](https://shiny.posit.co/) toolkit for building generative AI applications like chatbots and [streaming content](https://posit-dev.github.io/shinychat/r/reference/markdown_stream.html). It's designed to work alongside the [ellmer](https://ellmer.tidyverse.org/) package, which handles response generation.

## Installation

You can install shinychat from CRAN with:

``` r
install.packages("shinychat")
```

Or, install the development version of shinychat from [GitHub](https://github.com/) with:

``` r
# install.packages("pak")
pak::pak("posit-dev/shinychat/pkg-r")
```

## Example

To run this example, you'll first need to create an OpenAI API key, and set it in your environment as `OPENAI_API_KEY`.

You'll also need to install the [ellmer](https://ellmer.tidyverse.org/) package (with `install.packages("ellmer")`).

```r
library(shiny)
library(shinychat)

ui <- page_chat(
  "Assistant",
  id = "chat",
  messages = "**Hello!** How can I help you today?"
)

server <- function(input, output, session) {
  chat <-
    ellmer::chat_openai(
      system_prompt = "Respond to the user as succinctly as possible."
    )

  observeEvent(input$chat_user_input, {
    stream <- chat$stream_async(input$chat_user_input)
    chat_append("chat", stream)
  })
}

shinyApp(ui, server)
```

<img src="man/figures/app.png" alt="Screenshot of the resulting app." style="width: 100%"/>

## Next steps

Ready to start building a chatbot with shinychat? See [Get Started](https://posit-dev.github.io/shinychat/r/articles/get-started.html) to learn more.

Use `page_chat()` when the chat owns the full browser window. It includes
responsive navigation and sidebar support:

```r
ui <- page_chat(
  "Assistant",
  toolbar = actionButton("clear_chat", "Clear conversation"),
  toolbar_global = actionButton("help", "Help"),
  sidebar = chat_sidebar(tags$p("Tools"), history = FALSE),
  pages = list(
    chat_nav_panel(
      "About",
      tags$p("About this app."),
      value = "about",
    ),
    chat_nav_panel(
      "Settings",
      tags$p("Settings"),
      toolbar = actionButton("save_settings", "Save settings")
    )
  ),
  artifact = chat_artifact(tags$p("Preview content"), title = "Preview")
)
```

For an embedded chat or a layout with other top-level content, continue using
`chat_ui()` inside `bslib::page_fillable()`, `bslib::page_sidebar()`, or
another suitable container. `page_chat()` owns its page composition and should
not be wrapped in another page container.

The package includes credential-free `page_chat()` examples. Run them with:

```r
shiny::runExample("page-chat-navigation", package = "shinychat")
shiny::runExample("page-chat-artifact-controls", package = "shinychat")
```
