# Append an assistant response (or user message) to a chat control

The `chat_append` function appends a message to an existing
[`chat_ui()`](https://posit-dev.github.io/shinychat/r/dev/reference/chat_ui.md).
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
  tag) or a string of HTML. Pass `FALSE` to remove the icon for this
  message, or `TRUE` to use the default icon.

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

## Asides

An aside is a small pill that appears at the end of the paragraph or
list item it's attached to, showing a popover on hover, click, or
keyboard focus. Create one by writing (or prompting an LLM to write) an
inline `<shiny-aside>` tag anywhere in a block's markdown; the tag's
content becomes the popover body:

- `<shiny-aside label="a source name" url="https://...">markdown shown in the popover</shiny-aside>`

`label` controls the text on the identity chip. A safe `url` makes the
source heading in the popover a link. It also supplies a derived favicon
unless `icon` overrides it. Without a `label`, the aside falls back to a
plain numbered marker. The body is ordinary markdown: inline for a
one-liner, or — by separating it with blank lines — a rich block body
(paragraphs, lists, code) shown in the popover. Labeled asides in the
same paragraph or list item collapse into one pill, with each aside kept
as a separate popover page. Each unlabeled aside remains a separate
numbered pill. The grouped pill shows a `+N` overflow count only when
its labeled asides have different labels. Asides that share one label
use a single face with no count.

Set these CSS properties on the chat container to style aside markers:

- `--shiny-chat-aside-marker-color`

- `--shiny-chat-aside-marker-hover-color`

- `--shiny-chat-aside-marker-bg`

- `--shiny-chat-aside-marker-hover-bg`

- `--shiny-chat-aside-marker-font-family`

`grounded-span` identifies the answer text that is related to an aside.
Its value must exactly match text before the tag in the same paragraph
or list item. When the popover opens, shinychat highlights the most
recent match. If the value does not match, no text is highlighted.

Long content wraps and scrolls within the viewport. The popover keeps
the nearest scoped Bootstrap theme. In a paged popover, page changes are
announced to assistive technology without repeating the body.

Set `display="compact"` to show a compact numbered reference in the
message. The popover retains the source label. Compact asides in the
same paragraph or list item share a marker, such as `[2, 3]`. To style
only compact markers, set the CSS properties above on
`[data-shinychat-aside-display="compact"]`.

The favicon is fetched at render time from a third-party service
(DuckDuckGo's icon service), which receives the cited site's hostname.
To avoid that request — for privacy, or for offline/air-gapped
deployments — set the `SHINYCHAT_ASIDE_FAVICON` environment variable to
`false`. You can still set `icon` to a URL you control; an explicit
`icon` bypasses the lookup entirely.

**A labeled aside with a grounded span and a one-line body:**

    chat_append(
      "chat",
      paste0(
        "Hub motors are cheaper",
        paste0(
          '<shiny-aside label="eBicycles" ',
          'url="https://ebicycles.example/hub-vs-mid-drive" ',
          'grounded-span="Hub motors are cheaper">'
        ),
        "[Hub Motor vs. Mid-Drive Motor Differences Explained]",
        "(https://ebicycles.example/hub-vs-mid-drive)",
        "</shiny-aside>",
        ", and ideal for flatter terrain."
      )
    )

**Compact labeled asides that share one numbered marker:**

    chat_append(
      "chat",
      paste0(
        "Revenue is recognized at shipment",
        '<shiny-aside display="compact" label="Revenue policy">',
        "Exact revenue policy.</shiny-aside>",
        " and records are retained for 30 days",
        '<shiny-aside display="compact" label="Retention policy">',
        "Exact retention policy.</shiny-aside>."
      )
    )

**Two asides cited in the same sentence** collapse into one pill (the
first source's label becomes the face, with a "+1" overflow):

    chat_append(
      "chat",
      paste0(
        "Hub motors are cheaper",
        '<shiny-aside label="eBicycles" url="https://ebicycles.example">...</shiny-aside>',
        '<shiny-aside label="WIRED" url="https://wired.example">...</shiny-aside>',
        ", and ideal for flatter terrain."
      )
    )

**A label-less aside with a rich block body** (falls back to a plain
numbered pill):

    chat_append(
      "chat",
      paste0(
        "Battery quality matters more than raw power",
        "<shiny-aside>\n\n",
        "**Methodology**\n\n",
        "- 40 commuter e-bike models\n",
        "- released in 2024\n\n",
        "</shiny-aside>"
      )
    )

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
