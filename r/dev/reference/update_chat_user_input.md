# Update the user input of a chat control

Update the user input of a chat control

## Usage

``` r
update_chat_user_input(
  id,
  ...,
  value = NULL,
  placeholder = NULL,
  submit = FALSE,
  focus = FALSE,
  attachments = NULL,
  attachment_mode = c("append", "set"),
  session = getDefaultReactiveDomain()
)
```

## Arguments

- id:

  The ID of the chat element

- ...:

  Currently unused, but reserved for future use.

- value:

  The value to set the user input to. If `NULL`, the input will not be
  updated.

- placeholder:

  The placeholder text for the user input

- submit:

  Whether to automatically submit the text for the user. Requires
  `value`.

- focus:

  Whether to move focus to the input element. Requires `value` or
  non-empty `attachments`.

- attachments:

  A list of attachment objects created by
  [`chat_attachment()`](https://posit-dev.github.io/shinychat/r/dev/reference/chat_attachment.md).
  When `NULL` (default), any existing staged attachments are left
  unchanged. Pass an empty list
  ([`list()`](https://rdrr.io/r/base/list.html)) to clear staged
  attachments.

- attachment_mode:

  How to combine `attachments` with any already-staged attachments.
  `"append"` (default) adds to the existing set; `"set"` replaces it.
  Use `attachment_mode = "set"` with `attachments = list()` to clear all
  staged attachments.

- session:

  The Shiny session object

## Examples

``` r
if (FALSE) { # interactive()
library(shiny)
library(bslib)
library(shinychat)

ui <- page_fillable(
  chat_ui("chat"),
  layout_columns(
    fill = FALSE,
    actionButton("update_placeholder", "Update placeholder"),
    actionButton("update_value", "Update user input")
  )
)

server <- function(input, output, session) {
  observeEvent(input$update_placeholder, {
    update_chat_user_input("chat", placeholder = "New placeholder text")
  })

  observeEvent(input$update_value, {
    update_chat_user_input("chat", value = "New user input", focus = TRUE)
  })

  observeEvent(input$chat_user_input, {
    response <- paste0("You said: ", input$chat_user_input)
    chat_append("chat", response)
  })
}

shinyApp(ui, server)
}
```
