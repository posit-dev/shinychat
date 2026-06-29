# Open a live chat application in the browser

Create a simple Shiny app for live chatting using an
[ellmer::Chat](https://ellmer.tidyverse.org/reference/Chat.html) object.
Note that these functions will mutate the input `client` object as you
chat because your turns will be appended to the history.

The app created by `chat_app()` is suitable for interactive use by a
single user. For multi-user Shiny apps, use
[`chat_ui()`](https://posit-dev.github.io/shinychat/r/dev/reference/chat_ui.md)
and `chat_server()` and be sure to create a new chat client for each
user session.

## Usage

``` r
chat_app(client, ..., bookmark_store = "url", allow_attachments = TRUE)

chat_server(
  id,
  client,
  greeting = NULL,
  bookmark_on_input = TRUE,
  bookmark_on_response = TRUE,
  session = shiny::getDefaultReactiveDomain()
)
```

## Arguments

- client:

  A chat object created by ellmer, e.g.
  [`ellmer::chat_openai()`](https://ellmer.tidyverse.org/reference/chat_openai.html)
  and friends.

- ...:

  Additional arguments passed to
  [`shiny::shinyApp()`](https://rdrr.io/pkg/shiny/man/shinyApp.html).

- bookmark_store:

  The bookmarking store to use for the app. Passed to
  `enable_bookmarking` in
  [`shiny::shinyApp()`](https://rdrr.io/pkg/shiny/man/shinyApp.html).
  Defaults to `"url"`, which uses the URL to store the chat state.
  URL-based bookmarking is limited in size; use `"server"` to store the
  state on the server side without size limitations; or disable
  bookmarking by setting this to `"disable"`.

- allow_attachments:

  Controls the file-attachment affordance (an attach button, plus
  clipboard paste and drag-and-drop) in the chat input. `NULL` (default)
  defers to `chat_server()`, which enables attachments automatically.
  Pass `TRUE` to accept all supported types (PNG, JPEG, GIF, WebP, PDF,
  and common text/code files such as Markdown, plain text, CSV, JSON,
  and source files), `FALSE` to disable, or a character vector of MIME
  types to restrict what is accepted (each must be one of the supported
  types).

  The shape of `input$<id>_user_input` is determined by this argument,
  so it is predictable for a given app. When attachments are disabled
  (the default), it is the typed text as a character string, exactly as
  before. When attachments are enabled, it is always a list of ellmer
  [ellmer::Content](https://ellmer.tidyverse.org/reference/Content.html)
  objects (the typed text, if any, followed by one content object per
  attachment) - a list even when no files were attached. Splice the list
  into a chat method's `...` with `!!!`, e.g.
  `client$stream_async(!!!input$<id>_user_input)`. (No
  [`rlang::inject()`](https://rlang.r-lib.org/reference/inject.html) is
  needed: ellmer's chat methods collect `...` with dynamic dots.)

  The maximum combined size of all attachments in a single message is
  controlled globally by the `SHINYCHAT_MAX_ATTACHMENT_SIZE` environment
  variable (a raw byte count; defaults to approximately 30 MB). Files
  that would push the total over this cap are rejected in the browser
  with a notice.

- id:

  The ID of the chat element

- greeting:

  Optional greeting to set when the module initializes. Accepts a static
  value (string,
  [`htmltools::HTML()`](https://rstudio.github.io/htmltools/reference/HTML.html),
  [`htmltools::tagList()`](https://rstudio.github.io/htmltools/reference/tagList.html),
  or
  [`chat_greeting()`](https://posit-dev.github.io/shinychat/r/dev/reference/chat_greeting.md))
  or a **function** that generates the greeting dynamically. See the
  **Greeting** section below for details.

- bookmark_on_input:

  A logical value determines if the bookmark should be updated when the
  user submits a message. Default is `TRUE`.

- bookmark_on_response:

  A logical value determines if the bookmark should be updated when the
  response stream completes. Default is `TRUE`.

- session:

  The Shiny session. Defaults to the current reactive domain.

## Value

- `chat_app()` returns a
  [`shiny::shinyApp()`](https://rdrr.io/pkg/shiny/man/shinyApp.html)
  object.

- `chat_server()` includes the shinychat server logic, and returns an
  environment containing:

  - `last_input`: A reactive value containing the last user input (a
    string when attachments are disabled, a list of ellmer `Content`
    objects when enabled).

  - `last_turn`: A reactive value containing the last assistant turn.

  - `update_user_input()`: A function to update the chat input or submit
    a new user input. Takes the same arguments as
    [`update_chat_user_input()`](https://posit-dev.github.io/shinychat/r/dev/reference/update_chat_user_input.md),
    except for `id` and `session`, which are supplied automatically.

  - [`append()`](https://rdrr.io/r/base/append.html): A function to
    append a new message to the chat UI. Takes the same arguments as
    [`chat_append()`](https://posit-dev.github.io/shinychat/r/dev/reference/chat_append.md),
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

  - `set_greeting()`: A function to set, stream, or clear the chat
    greeting. Pass a
    [`chat_greeting()`](https://posit-dev.github.io/shinychat/r/dev/reference/chat_greeting.md)
    object, a plain string, or `NULL` to clear. Streaming greetings run
    inside an
    [shiny::ExtendedTask](https://rdrr.io/pkg/shiny/man/ExtendedTask.html)
    so the session stays responsive; if called while a greeting is
    already streaming, the new greeting is queued. If the greeting has
    already been dismissed, calling `set_greeting()` updates the content
    but does not make it visible again; call `clear(greeting = TRUE)`
    first to show a new greeting after dismissal.

  - `status`: A reactive value indicating the current chat interaction
    state. Returns `"idle"` when no response is in progress, or
    `"streaming"` while a response is actively being received.

  - `client`: The current chat client object (an active binding that
    always reflects the latest client, even after `set_client()` is
    called).

  - `set_client(new_client, sync = TRUE)`: Replace the chat client used
    by the module. When `sync` is `TRUE` (the default), the new client
    inherits conversation turns, system prompt, and tools from the
    previous client so the conversation continues seamlessly. Set
    `sync = FALSE` to use the new client as-is. If a response is
    currently streaming, the swap is deferred until the stream
    completes. If called multiple times while streaming, only the most
    recent new client is used.

  - `slash_command(name, description, handler, ..., echo, force)`:
    Register a slash command. `handler` is required: pass a function
    (taking 0 or 1 argument), or `NULL` for a client-side command
    handled in JavaScript via the `shiny:chat-slash-command` DOM event.
    A handler that takes one argument receives a
    [ContentSlashCommand](https://posit-dev.github.io/shinychat/r/dev/reference/ContentSlashCommand.md)
    object (not a plain string). See
    [ContentSlashCommand](https://posit-dev.github.io/shinychat/r/dev/reference/ContentSlashCommand.md)
    for details on how to use this object to preserve the original
    command text across bookmarks. `echo` controls whether invoking the
    command is echoed as a user message and awaits a response; it
    defaults to `TRUE` when a handler is given and `FALSE` otherwise
    (set `echo = FALSE` for a handler that only performs side effects).
    Returns a function that removes the command. Errors if a command
    with the same name is already registered unless `force = TRUE`.

## Functions

- `chat_app()`: A simple Shiny app for live chatting. Note that this app
  is suitable for interactive use by a single user; do not use
  `chat_app()` in a multi-user Shiny app context.

- `chat_server()`: Wire up batteries-included chat server logic in a
  Shiny session.

## Greeting

When `greeting` is a **function**, it is called each time the
`greeting_requested` event fires — on first view when the chat is empty,
and again after `clear(greeting = TRUE)`. The function should return a
[`chat_greeting()`](https://posit-dev.github.io/shinychat/r/dev/reference/chat_greeting.md)
(typically wrapping a stream). Static values (strings,
[`chat_greeting()`](https://posit-dev.github.io/shinychat/r/dev/reference/chat_greeting.md)
objects) are set once at init and do not regenerate.

The function signature determines what is passed. Currently the only
recognized argument is `client`.

**`function(client)`** (recommended). A clone of the `client` with its
turn history wiped is passed as `client`. This avoids manually creating
and configuring a separate client:

    chat_server("chat", client, greeting = function(client) {
      stream <- client$stream_async("Generate a short welcome message.")
      chat_greeting(stream)
    })

**`function()`** (zero arguments). You create and manage your own
client:

    chat_server("chat", client, greeting = function() {
      greeter <- ellmer::chat_openai(model = "gpt-4o")
      stream <- greeter$stream_async("Generate a short welcome message.")
      chat_greeting(stream)
    })

**Static value.** Set once; does not regenerate after `clear()`:

    chat_server("chat", client, greeting = "## Welcome!\n\nHow can I help?")

The returned `set_greeting()` helper is available for cases where you
need to set a greeting outside the greeting lifecycle.

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
      chat_ui(
        "claude",
        messages = list(
          "Hi! Use this chat interface to chat with Anthropic's `claude-3-5-sonnet`."
        )
      )
    ),
    card(
      card_header("Chat with ChatGPT"),
      chat_ui(
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

  chat_server("claude", claude)
  chat_server("openai", openai)
}

shinyApp(ui, server)
} # }
```
