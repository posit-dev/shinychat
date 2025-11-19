# Add Shiny bookmarking for shinychat

Adds Shiny bookmarking hooks to save and restore the ellmer chat
`client`. Also restores chat messages from the history in the `client`.

If either `bookmark_on_input` or `bookmark_on_response` is `TRUE`, the
Shiny App's bookmark will be automatically updated without showing a
modal to the user.

Note: Only the `client`'s chat state is saved/restored in the bookmark.
If the `client`'s state doesn't properly capture the chat's UI (i.e., a
transformation is applied in-between receiving and displaying the
message), then you may need to implement your own `session$onRestore()`
(and possibly `session$onBookmark`) handler to restore any additional
state.

To avoid restoring chat history from the `client`, you can ensure that
the history is empty by calling `client$set_turns(list())` before
passing the client to `chat_restore()`.

## Usage

``` r
chat_restore(
  id,
  client,
  ...,
  bookmark_on_input = TRUE,
  bookmark_on_response = TRUE,
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

- session:

  The Shiny session object

## Value

Returns nothing (`invisible(NULL)`).

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
