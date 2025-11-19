# Stream markdown content

Streams markdown content into a
[`output_markdown_stream()`](https://posit-dev.github.io/shinychat/r/reference/output_markdown_stream.md)
UI element. A markdown stream can be useful for displaying generative AI
responses (outside of a chat interface), streaming logs, or other use
cases where chunks of content are generated over time.

## Usage

``` r
markdown_stream(
  id,
  content_stream,
  operation = c("replace", "append"),
  session = getDefaultReactiveDomain()
)
```

## Arguments

- id:

  The ID of the markdown stream to stream content to.

- content_stream:

  A string generator (e.g.,
  [`coro::generator()`](https://coro.r-lib.org/reference/generator.html)
  or
  [`coro::async_generator()`](https://coro.r-lib.org/reference/async_generator.html)),
  a string promise (e.g.,
  [`promises::promise()`](https://rstudio.github.io/promises/reference/promise.html)),
  or a string promise generator.

- operation:

  The operation to perform on the markdown stream. The default,
  `"replace"`, will replace the current content with the new content
  stream. The other option, `"append"`, will append the new content
  stream to the existing content.

- session:

  The Shiny session object.

## Examples

``` r
if (FALSE) { # interactive()

library(shiny)
library(coro)
library(bslib)
library(shinychat)

# Define a generator that yields a random response
# (imagine this is a more sophisticated AI generator)
random_response_generator <- async_generator(function() {
  responses <- c(
    "What does that suggest to you?",
    "I see.",
    "I'm not sure I understand you fully.",
    "What do you think?",
    "Can you elaborate on that?",
    "Interesting question! Let's examine thi... **See more**"
  )

  await(async_sleep(1))
  for (chunk in strsplit(sample(responses, 1), "")[[1]]) {
    yield(chunk)
    await(async_sleep(0.02))
  }
})

ui <- page_fillable(
  actionButton("generate", "Generate response"),
  output_markdown_stream("stream")
)

server <- function(input, output, session) {
  observeEvent(input$generate, {
    markdown_stream("stream", random_response_generator())
  })
}

shinyApp(ui, server)
}
```
