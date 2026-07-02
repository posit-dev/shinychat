# Add Shiny bookmarking for shinychat

Adds Shiny bookmarking hooks to save and restore the ellmer chat
`client`. Also restores chat messages from the history in the `client`.

If either `bookmark_on_input` or `bookmark_on_response` is `TRUE`, the
Shiny App's bookmark will be automatically updated without showing a
modal to the user.

Note: The `client`'s chat state and the greeting content are both
saved/restored automatically. If the `client`'s state doesn't properly
capture the chat's UI (i.e., a transformation is applied in-between
receiving and displaying the message), you may need to implement your
own `session$onRestore()` (and possibly `session$onBookmark`) handler to
restore any additional state.

To avoid restoring chat history from the `client`, you can ensure that
the history is empty by calling `client$set_turns(list())` before
passing the client to `chat_restore()`.

`chat_restore()` bookmarks the whole session and doesn't know about
multiple conversations. If you need per-conversation history (the chat
history drawer, switching between saved conversations), use
[`chat_enable_history()`](https://posit-dev.github.io/shinychat/r/dev/reference/chat_enable_history.md)
with `history_options(restore_mode = "bookmark")` instead — it replaces
`chat_restore()`'s job for history-aware apps. The two are mutually
exclusive;
[`chat_app()`](https://posit-dev.github.io/shinychat/r/dev/reference/chat_app.md)
picks one or the other based on whether `history` is set.

## Usage

``` r
chat_restore(
  id,
  client,
  ...,
  bookmark_on_input = TRUE,
  bookmark_on_response = TRUE,
  restore_ui = TRUE,
  session = getDefaultReactiveDomain()
)
```

## Arguments

- id:

  The ID of the chat element

- client:

  The ellmer LLM chat client.

- ...:

  Used for future parameter expansion.

- bookmark_on_input:

  A logical value determines if the bookmark should be updated when the
  user submits a message. Default is `TRUE`.

- bookmark_on_response:

  A logical value determines if the bookmark should be updated when the
  response stream completes. Default is `TRUE`.

- restore_ui:

  Whether to render the client's existing turns into the chat UI on
  registration. Default is `TRUE`. Set to `FALSE` when re-registering
  bookmarks after a client swap (where the UI already reflects the
  conversation).

- session:

  The Shiny session object

## Value

Invisibly returns a function that, when called, cancels all bookmark
registrations made by this call. This is useful when swapping the chat
client: cancel the previous bookmarks, then call `chat_restore()` again
with the new client.

## Examples

``` r
if (FALSE) { # interactive()
library(shiny)
library(bslib)
library(shinychat)

ui <- function(request) {
  page_fillable(
    chat_ui("chat", fill = TRUE)
  )
}

server <- function(input, output, session) {
  chat_client <- ellmer::chat_ollama(
    system_prompt = "Important: Always respond in a limerick",
    model = "qwen2.5-coder:1.5b",
    echo = TRUE
  )
  # Update bookmark to chat on user submission and completed response
  chat_restore("chat", chat_client)

  observeEvent(input$chat_user_input, {
    stream <- chat_client$stream_async(input$chat_user_input)
    chat_append("chat", stream)
  })
}

# Enable bookmarking!
shinyApp(ui, server, enableBookmarking = "server")
}
```
