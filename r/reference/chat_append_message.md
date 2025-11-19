# Low-level function to append a message to a chat control

For advanced users who want to control the message chunking behavior.
Most users should use
[`chat_append()`](https://posit-dev.github.io/shinychat/r/reference/chat_append.md)
instead.

## Usage

``` r
chat_append_message(
  id,
  msg,
  chunk = TRUE,
  operation = c("append", "replace"),
  icon = NULL,
  session = getDefaultReactiveDomain()
)
```

## Arguments

- id:

  The ID of the chat element

- msg:

  The message to append. Should be a named list with `role` and
  `content` fields. The `role` field should be either "user" or
  "assistant". The `content` field should be a string containing the
  message content, in Markdown format.

- chunk:

  Whether `msg` is just a chunk of a message, and if so, what type. If
  `FALSE`, then `msg` is a complete message. If `"start"`, then `msg` is
  the first chunk of a multi-chunk message. If `"end"`, then `msg` is
  the last chunk of a multi-chunk message. If `TRUE`, then `msg` is an
  intermediate chunk of a multi-chunk message. Default is `FALSE`.

- operation:

  The operation to perform on the message. If `"append"`, then the new
  content is appended to the existing message content. If `"replace"`,
  then the existing message content is replaced by the new content.
  Ignored if `chunk` is `FALSE`.

- icon:

  An optional icon to display next to the message, currently only used
  for assistant messages. The icon can be any HTML element (e.g.,
  [`htmltools::img()`](https://rstudio.github.io/htmltools/reference/builder.html)
  tag) or a string of HTML.

- session:

  The Shiny session object

## Value

Returns nothing (`invisible(NULL)`).

## Examples

``` r
if (FALSE) { # interactive()
library(shiny)
library(coro)
library(bslib)
library(shinychat)

# Dumbest chatbot in the world: ignores user input and chooses
# a random, vague response.
fake_chatbot <- async_generator(function(id, input) {
  responses <- c(
    "What does that suggest to you?",
    "I see.",
    "I'm not sure I understand you fully.",
    "What do you think?",
    "Can you elaborate on that?",
    "Interesting question! Let's examine thi... **See more**"
  )

  # Use low-level chat_append_message() to temporarily set a progress message
  chat_append_message(id, list(role = "assistant", content = "_Thinking..._ "))
  await(async_sleep(1))
  # Clear the progress message
  chat_append_message(id, list(role = "assistant", content = ""), operation = "replace")

  for (chunk in strsplit(sample(responses, 1), "")[[1]]) {
    yield(chunk)
    await(async_sleep(0.02))
  }
})

ui <- page_fillable(
  chat_ui("chat", fill = TRUE)
)

server <- function(input, output, session) {
  observeEvent(input$chat_user_input, {
    response <- fake_chatbot("chat", input$chat_user_input)
    chat_append("chat", response)
  })
}

shinyApp(ui, server)
}
```
