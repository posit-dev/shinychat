# Open a live chat application in the browser

Create a simple Shiny app for live chatting using an
[ellmer::Chat](https://ellmer.tidyverse.org/reference/Chat.html) object.
Note that these functions will mutate the input `client` object as you
chat because your turns will be appended to the history.

The app created by `chat_app()` is suitable for interactive use by a
single user. For multi-user Shiny apps, use the Shiny module chat
functions – `chat_mod_ui()` and `chat_mod_server()` – and be sure to
create a new chat client for each user session.

## Usage

``` r
chat_app(client, ..., bookmark_store = "url")

chat_mod_ui(id, ..., client = deprecated(), messages = NULL)

chat_mod_server(
  id,
  client,
  bookmark_on_input = TRUE,
  bookmark_on_response = TRUE
)
```

## Arguments

- client:

  A chat object created by ellmer, e.g.
  [`ellmer::chat_openai()`](https://ellmer.tidyverse.org/reference/chat_openai.html)
  and friends. This argument is deprecated in `chat_mod_ui()` because
  the client state is now managed by `chat_mod_server()`.

- ...:

  In `chat_app()`, additional arguments are passed to
  [`shiny::shinyApp()`](https://rdrr.io/pkg/shiny/man/shinyApp.html). In
  `chat_mod_ui()`, additional arguments are passed to
  [`chat_ui()`](https://posit-dev.github.io/shinychat/r/reference/chat_ui.md).

- bookmark_store:

  The bookmarking store to use for the app. Passed to
  `enable_bookmarking` in
  [`shiny::shinyApp()`](https://rdrr.io/pkg/shiny/man/shinyApp.html).
  Defaults to `"url"`, which uses the URL to store the chat state.
  URL-based bookmarking is limited in size; use `"server"` to store the
  state on the server side without size limitations; or disable
  bookmarking by setting this to `"disable"`.

- id:

  The chat module ID.

- messages:

  Initial messages shown in the chat, used only when `client` (in
  `chat_mod_ui()`) doesn't already contain turns. Passed to `messages`
  in
  [`chat_ui()`](https://posit-dev.github.io/shinychat/r/reference/chat_ui.md).

- bookmark_on_input:

  A logical value determines if the bookmark should be updated when the
  user submits a message. Default is `TRUE`.

- bookmark_on_response:

  A logical value determines if the bookmark should be updated when the
  response stream completes. Default is `TRUE`.

## Value

- `chat_app()` returns a
  [`shiny::shinyApp()`](https://rdrr.io/pkg/shiny/man/shinyApp.html)
  object.

- `chat_mod_ui()` returns the UI for a shinychat module.

- `chat_mod_server()` includes the shinychat module server logic, and
  returns a list containing:

  - `last_input`: A reactive value containing the last user input.

  - `last_turn`: A reactive value containing the last assistant turn.

  - `update_user_input()`: A function to update the chat input or submit
    a new user input. Takes the same arguments as
    [`update_chat_user_input()`](https://posit-dev.github.io/shinychat/r/reference/update_chat_user_input.md),
    except for `id` and `session`, which are supplied automatically.

  - [`append()`](https://rdrr.io/r/base/append.html): A function to
    append a new message to the chat UI. Takes the same arguments as
    [`chat_append()`](https://posit-dev.github.io/shinychat/r/reference/chat_append.md),
    except for `id` and `session`, which are supplied automatically.

  - `clear()`: A function to clear the chat history and the chat UI.
    `clear()` takes an optional list of `messages` used to initialize
    the chat after clearing. `messages` should be a list of messages,
    where each message is a list with `role` and `content` fields. The
    `client_history` argument controls how the chat client's history is
    updated after clearing. It can be one of: `"clear"` the chat
    history; `"set"` the chat history to `messages`; `"append"`
    `messages` to the existing chat history; or `"keep"` the existing
    chat history.

  - `client`: The chat client object, which is mutated as you chat.

## Functions

- `chat_app()`: A simple Shiny app for live chatting. Note that this app
  is suitable for interactive use by a single user; do not use
  `chat_app()` in a multi-user Shiny app context.

- `chat_mod_ui()`: A simple chat app module UI.

- `chat_mod_server()`: A simple chat app module server.

## Examples

``` r
if (FALSE) { # \dontrun{
# Interactive in the console ----
client <- ellmer::chat_anthropic()
chat_app(client)

# Inside a Shiny app ----
library(shiny)
library(bslib)
library(shinychat)

ui <- page_fillable(
  titlePanel("shinychat example"),

  layout_columns(
    card(
      card_header("Chat with Claude"),
      chat_mod_ui(
        "claude",
        messages = list(
          "Hi! Use this chat interface to chat with Anthropic's `claude-3-5-sonnet`."
        )
      )
    ),
    card(
      card_header("Chat with ChatGPT"),
      chat_mod_ui(
        "openai",
        messages = list(
          "Hi! Use this chat interface to chat with OpenAI's `gpt-4o`."
        )
      )
    )
  )
)

server <- function(input, output, session) {
  claude <- ellmer::chat_anthropic(model = "claude-3-5-sonnet-latest") # Requires ANTHROPIC_API_KEY
  openai <- ellmer::chat_openai(model = "gpt-4o") # Requires OPENAI_API_KEY

  chat_mod_server("claude", claude)
  chat_mod_server("openai", openai)
}

shinyApp(ui, server)
} # }
```
