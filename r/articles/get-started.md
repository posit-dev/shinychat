# Get started

This article will cover how to build a chatbot powered by a Large
Language Model (LLM) using shinychat and
[ellmer](https://ellmer.tidyverse.org/). ellmer will handle connecting
to and communicating with the model, while shinychat will handle the
user interface for your chatbot.

You will need to install both shinychat and ellmer.

``` r
install.packages(c("shinychat", "ellmer"))
```

## Setup

### Choose a model

First, choose a model to power your chatbot. ellmer and shinychat
support a [wide variety](https://ellmer.tidyverse.org/#providers) of LLM
providers including Anthropic, OpenAI, Vertex, Snowflake, Groq,
Perplexity, and more.

With ellmer, you specify the LLM provider by choosing the corresponding
`chat_*()` function, e.g.,
[`chat_anthropic()`](https://ellmer.tidyverse.org/reference/chat_anthropic.html),
[`chat_openai()`](https://ellmer.tidyverse.org/reference/chat_openai.html),
etc. This makes it easy to swap out the chat provider to a different one
at any time.

Model providers also typically offer a variety of models. To specify a
particular model, use the `chat_*()` function’s `model` argument. For
example:

``` r
ellmer::chat_openai(model = "o3")
```

If you don’t specify the `model` argument, the `chat_*()` function will
use a reasonable default. For more information, see the individual
`chat_*()` function’s
[documentation](https://ellmer.tidyverse.org/reference/index.html#chatbots).

Help me choose!

If you’re not sure which provider to choose, ellmer provides a
[guide](https://ellmer.tidyverse.org/#providermodel-choice) to help you
decide.

### Set up credentials

Next, authenticate with your LLM provider. Popular model providers like
OpenAI and Anthropic require an API key. We recommend storing these API
keys in your `.Renviron` (e.g., as `OPENAI_API_KEY` or
`ANTHROPIC_API_KEY`).

You can find some helpful links and tips for getting set up with
credentials (e.g., an API key) on the relevant reference page for the
`chat_*()` provider you’d like to work with
([`chat_openai()`](https://ellmer.tidyverse.org/reference/chat_openai.html),
[`chat_anthropic()`](https://ellmer.tidyverse.org/reference/chat_anthropic.html)).

## Create a basic chatbot

Once you’ve identified which model provider you want to use and set up
the necessary credentials, you’re ready to create a chatbot. The
following code creates a basic chatbot in a Shiny app.

Copy and paste the code into an R script, switching out
[`ellmer::chat_openai()`](https://ellmer.tidyverse.org/reference/chat_openai.html)
for your desired chat function. Save the file as `app.R` and then run
the app.

``` r
library(shiny)
library(shinychat)

ui <- bslib::page_fluid(
  chat_ui("chat")
)

server <- function(input, output, session) {
  chat <- ellmer::chat_openai()
  
  observeEvent(input$chat_user_input, {
    stream <- chat$stream_async(input$chat_user_input)
    chat_append("chat", stream)
  })
}

shinyApp(ui, server)
```

Congrats, you now have a chat interface powered by an LLM of your
choice! 🎉

![Screenshot of a conversation using
shinychat.](images/chat-quick-start.png)

Screenshot of a conversation using shinychat.

### Inspect the code

Let’s take a closer look at the code in `app.R`.

``` r
library(shiny)
library(shinychat)

ui <- bslib::page_fluid(
  # Add a chat UI element
  chat_ui("chat")
)

server <- function(input, output, session) {
  # Initialize a chat with your chosen model provider
  chat <- ellmer::chat_openai(system_prompt = "You are a helpful assistant.")
  
  # Listen for user input and communicate with the model
  observeEvent(input$chat_user_input, {
    stream <- chat$stream_async(input$chat_user_input)
    chat_append("chat", stream)
  })
}

shinyApp(ui, server)
```

A shinychat chatbot includes three core steps:

1.  **Create a chat UI element** with
    [`chat_ui()`](https://posit-dev.github.io/shinychat/reference/chat_ui.html).

2.  **Initialize a chat** with a `chat_*()` function, like
    [`chat_openai()`](https://ellmer.tidyverse.org/reference/chat_openai.html),
    in the server function. Use a different `chat_*()` function
    ([`chat_ollama()`](https://ellmer.tidyverse.org/reference/chat_ollama.html),
    [`chat_anthropic()`](https://ellmer.tidyverse.org/reference/chat_anthropic.html),
    etc.) to use a different model provider. You can also use the
    `system_prompt` argument to supply a [system
    prompt](https://ellmer.tidyverse.org/articles/prompt-design.html).

3.  **Set up a reactive listener** with
    [`observeEvent()`](https://rdrr.io/pkg/shiny/man/observeEvent.html)
    that waits for the user to submit a message
    (`input$chat_user_input`). When a message is received:

    - Send the input to the LLM using `chat$stream_async()`, which
      returns asynchronously streaming results from the LLM. This means
      the results will appear in chunks, so the user doesn’t have to
      wait for the full response.
    - Append the response to the
      [`chat_ui()`](https://posit-dev.github.io/shinychat/r/reference/chat_ui.md)
      element with
      [`chat_append()`](https://posit-dev.github.io/shinychat/r/reference/chat_append.md),
      so the user can see the model’s reply appear live as it’s
      generated.

### Add a system prompt

Use the `chat_*()` function’s `system_prompt` argument to provide the
LLM with more information about how you would like it to behave.

``` r
chat <- ellmer::chat_ollama(system_prompt = "You are a helpful assistant")
```

To learn more about writing system prompts, see ellmer’s [Prompt
design](https://ellmer.tidyverse.org/articles/prompt-design.html)
vignette. Generally, we recommend writing the system prompt in a
separate markdown file, but if your prompt is short you can also supply
it directly as a string to the `system_prompt` argument.

### Add messages and suggestions

#### On startup

You can specify messages to show when the chat first loads by using
[`chat_ui()`](https://posit-dev.github.io/shinychat/r/reference/chat_ui.md)’s
`messages` argument. You can use markdown or HTML to format these
messages.

``` r
chat_ui(
    id = "chat",
    messages = "**Hello!** How can I help you today?"
)
```

![Screenshot of a chatbot with a welcome
message.](images/chat-messages.png)

Screenshot of a chatbot with a welcome message.

You can also suggest inputs to the user by adding the `suggestion` CSS
class to the relevant portions of the message. Similarly, use the
`submit` class to make clicking on the suggestion submit the input
automatically.

``` r
messages <-
  '
  **Hello!** How can I help you today?

  Here are a couple suggestions:

  * <span class="suggestion">Tell me a joke</span>
  * <span class="suggestion submit">Tell me a story</span>
  '

ui <- bslib::page_fillable(
  chat_ui(
    id = "chat",
    messages = messages
  )
)
```

![Screenshot of a chatbot with input
suggestions.](images/chat-suggestions.png)

Screenshot of a chatbot with input suggestions.

Messages can also contain arbitrary Shiny UI
[components](https://shiny.posit.co/r/components/), so you could even
include something like a
[tooltip](https://shiny.posit.co/r/components/display-messages/tooltips/)
to provide additional details on demand.

#### Mid-conversation

You can also use suggestions to guide users through a multi-turn
conversation. To do so, you’ll need to instruct the AI how to generate
suggestions itself by adding a section like the one below to your system
prompt:

    ## Showing prompt suggestions

    If you find it appropriate to suggest prompts the user might want to write, wrap the text of each prompt in `<span class="suggestion">` tags.
    Also use "Suggested next steps:" to introduce the suggestions. For example:

    ```
    Suggested next steps:

    1. <span class="suggestion">Suggestion 1.</span>
    2. <span class="suggestion">Suggestion 2.</span>
    3. <span class="suggestion">Suggestion 3.</span>
    ```

## Layouts

### Screen-filling layout

Use
[`page_fillable()`](https://rstudio.github.io/bslib/reference/page_fillable.html)
with `fillable_mobile = TRUE` if you want the chatbot input to stay
anchored at the bottom of the page and the chat to fill the remaining
space.

``` r
ui <- bslib::page_fillable(
  chat_ui("chat", messages = "Welcome!"),
  fillable_mobile = TRUE
)
```

![Screenshot of a chatbot filling the
page.](images/chat-page_fillable.png)

Screenshot of a chatbot filling the page.

### Sidebar layout

It can also be useful to place the chat in a sidebar, to free up the
main panel for other components. Use
[`page_sidebar()`](https://rstudio.github.io/bslib/reference/page_sidebar.html)
to create a sidebar page. Then, set the chat and sidebar’s heights to
`100%` so that the chat element fills the sidebar.

``` r
library(shiny)
library(bslib)
library(shinychat)

ui <- bslib::page_sidebar(
  sidebar = sidebar(
    chat_ui(
      "chat",
      messages = list(
        "Welcome! Here is a <span class='suggestion'>suggestion</span>."
      ),
      height = "100%"
    ),
    width = 300,
    style = "height: 100%;"
  ),
  "Main content",
  fillable = TRUE
)

server <- function(input, output, session) {
  chat <- ellmer::chat_openai()
  
  observeEvent(input$chat_user_input, {
    stream <- chat$stream_async(input$chat_user_input)
    chat_append("chat", stream)
  })
}

shinyApp(ui, server)
```

![Screenshot of a chatbot filling a sidebar.](images/chat-sidebar.png)

Screenshot of a chatbot filling a sidebar.

### Card layout

Embedding the chat component inside a
[`card()`](https://rstudio.github.io/bslib/reference/card.html) can help
visually separate the chat from the rest of the app. You can also add a
card header to include more information about your chatbot (perhaps with
a
[tooltip](https://shiny.posit.co/r/components/display-messages/tooltips/)).

[Cards](https://rstudio.github.io/bslib/articles/cards/) also come with
other handy features like `full_screen = TRUE` to make the chat
full-screen when embedded inside a larger app.

``` r
library(shiny)
library(bslib)
library(shinychat)

ui <- page_fillable(
  card(
    card_header(
      "Welcome to Posit chat",
      tooltip(icon("question"), "This chat is brought to you by Posit."),
      class = "d-flex justify-content-between align-items-center"
    ),
    chat_ui(
      id = "chat",
      messages = "Hello! How can I help you today?"
    )
  ),
  fillable_mobile = TRUE
)

server <- function(input, output, session) {
  chat <- ellmer::chat_openai()
  
  observeEvent(input$chat_user_input, {
    stream <- chat$stream_async(input$chat_user_input)
    chat_append("chat", stream)
  })
}

shinyApp(ui, server)
```

![Screenshot of a chatbot embedded in a card with a header and
tooltip.](images/chat-card.png)

Screenshot of a chatbot embedded in a card with a header and tooltip.
