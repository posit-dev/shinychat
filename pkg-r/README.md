# shinychat <a href="https://posit-dev.github.io/shinychat/r/"><img src="man/figures/logo.svg" align="right" height="138" alt="shinychat for R website" /></a>

<!-- badges: start -->
[![R-CMD-check](https://github.com/posit-dev/shinychat/actions/workflows/R-CMD-check.yaml/badge.svg)](https://github.com/posit-dev/shinychat/actions/workflows/R-CMD-check.yaml)
<!-- badges: end -->

Chat UI component for [Shiny for R](https://shiny.posit.co/).

(For [Shiny for Python](https://shiny.posit.co/py/), see [ui.Chat](https://shiny.posit.co/py/components/display-messages/chat/).)

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

You'll also need to install the {[ellmer](https://ellmer.tidyverse.org/)} package (with `install.packages("ellmer")`).

```r
library(shiny)
library(shinychat)

ui <- bslib::page_fluid(
  chat_ui("chat")
)

server <- function(input, output, session) {
  chat <- ellmer::chat_openai(system_prompt = "You're a trickster who answers in riddles")

  observeEvent(input$chat_user_input, {
    stream <- chat$stream_async(input$chat_user_input)
    chat_append("chat", stream)
  })
}

shinyApp(ui, server)
```
