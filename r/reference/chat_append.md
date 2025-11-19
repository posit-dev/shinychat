# Append an assistant response (or user message) to a chat control

The `chat_append` function appends a message to an existing
[`chat_ui()`](https://posit-dev.github.io/shinychat/r/reference/chat_ui.md).
The `response` can be a string, string generator, string promise, or
string promise generator (as returned by the 'ellmer' package's `chat`,
`stream`, `chat_async`, and `stream_async` methods, respectively).

This function should be called from a Shiny app's server. It is
generally used to append the client's response to the chat, while user
messages are added to the chat UI automatically by the front-end. You'd
only need to use `chat_append(role="user")` if you are programmatically
generating queries from the server and sending them on behalf of the
user, and want them to be reflected in the UI.

## Usage

``` r
chat_append(
  id,
  response,
  role = c("assistant", "user"),
  icon = NULL,
  session = getDefaultReactiveDomain()
)
```

## Arguments

- id:

  The ID of the chat element

- response:

  The message or message stream to append to the chat element. The
  actual message content can one of the following:

  - A string, which is interpreted as markdown and rendered to HTML on
    the client.

    - To prevent interpreting as markdown, mark the string as
      [`htmltools::HTML()`](https://rstudio.github.io/htmltools/reference/HTML.html).

  - A UI element.

    - This includes
      [`htmltools::tagList()`](https://rstudio.github.io/htmltools/reference/tagList.html),
      which take UI elements (including strings) as children. In this
      case, strings are still interpreted as markdown as long as they're
      not inside HTML.

- role:

  The role of the message (either "assistant" or "user"). Defaults to
  "assistant".

- icon:

  An optional icon to display next to the message, currently only used
  for assistant messages. The icon can be any HTML element (e.g., an
  [`htmltools::img()`](https://rstudio.github.io/htmltools/reference/builder.html)
  tag) or a string of HTML.

- session:

  The Shiny session object

## Value

Returns a promise that resolves to the contents of the stream, or an
error. This promise resolves when the message has been successfully sent
to the client; note that it does not guarantee that the message was
actually received or rendered by the client. The promise rejects if an
error occurs while processing the response (see the "Error handling"
section).

## Error handling

If the `response` argument is a generator, promise, or promise
generator, and an error occurs while producing the message (e.g., an
iteration in `stream_async` fails), the promise returned by
`chat_append` will reject with the error. If the `chat_append` call is
the last expression in a Shiny observer, shinychat will log the error
message and show a message that the error occurred in the chat UI.

## Examples

``` r
if (FALSE) { # interactive()
library(shiny)
library(coro)
library(bslib)
library(shinychat)

# Dumbest chatbot in the world: ignores user input and chooses
# a random, vague response.
fake_chatbot <- async_generator(function(input) {
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
  chat_ui("chat", fill = TRUE)
)

server <- function(input, output, session) {
  observeEvent(input$chat_user_input, {
    response <- fake_chatbot(input$chat_user_input)
    chat_append("chat", response)
  })
}

shinyApp(ui, server)
}
```
