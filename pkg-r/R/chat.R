#' @include shinychat-package.R
NULL

# This is a stripped-down port of the ui.Chat feature in py-shiny. The main
# things it's missing are server-side state management, i.e. the py-shiny
# version will keep the list of messages for you, and will handle the
# trimming of the message history to fit within the context window; these
# are left for the caller to handle in the R version.

chat_deps <- function() {
  htmltools::htmlDependency(
    "shinychat",
    utils::packageVersion("shinychat"),
    package = "shinychat",
    src = "lib/shiny",
    script = list(
      list(src = "chat/chat.js", type = "module"),
      list(src = "markdown-stream/markdown-stream.js", type = "module")
    ),
    stylesheet = c(
      "chat/chat.css",
      "markdown-stream/markdown-stream.css"
    )
  )
}

#' Create a chat UI element
#'
#' @description
#' Inserts a chat UI element into a Shiny UI, which includes a scrollable
#' section for displaying chat messages, and an input field for the user to
#' enter new messages.
#'
#' To respond to user input, listen for `input$ID_user_input` (for example, if
#' `id="my_chat"`, user input will be at `input$my_chat_user_input`), and use
#' [chat_append()] to append messages to the chat.
#'
#' @param id The ID of the chat element
#' @param ... Extra HTML attributes to include on the chat element
#' @param messages A list of messages to prepopulate the chat with. Each
#'   message can be one of the following:
#'
#'   * A string, which is interpreted as markdown and rendered to HTML on
#'     the client.
#'     * To prevent interpreting as markdown, mark the string as
#'       [htmltools::HTML()].
#'   * A UI element.
#'     * This includes [htmltools::tagList()], which take UI elements
#'       (including strings) as children. In this case, strings are still
#'       interpreted as markdown as long as they're not inside HTML.
#'   * A named list of `content` and `role`. The `content` can contain content
#'     as described above, and the `role` can be "assistant" or "user".
#'
#' @param placeholder The placeholder text for the chat's user input field
#' @param width The CSS width of the chat element
#' @param height The CSS height of the chat element
#' @param fill Whether the chat element should try to vertically fill its
#'   container, if the container is
#'   [fillable](https://rstudio.github.io/bslib/articles/filling/index.html)
#' @param icon_assistant The icon to use for the assistant chat messages.
#'   Can be HTML or a tag in the form of [htmltools::HTML()] or
#'   [htmltools::tags()]. If `None`, a default robot icon is used.
#' @returns A Shiny tag object, suitable for inclusion in a Shiny UI
#'
#' @examplesIf interactive()
#' library(shiny)
#' library(bslib)
#' library(shinychat)
#'
#' ui <- page_fillable(
#'   chat_ui("chat", fill = TRUE)
#' )
#'
#' server <- function(input, output, session) {
#'   observeEvent(input$chat_user_input, {
#'     # In a real app, this would call out to a chat client or API,
#'     # perhaps using the 'ellmer' package.
#'     response <- paste0(
#'       "You said:\n\n",
#'       "<blockquote>",
#'       htmltools::htmlEscape(input$chat_user_input),
#'       "</blockquote>"
#'     )
#'     chat_append("chat", response)
#'     chat_append("chat", stream)
#'   })
#' }
#'
#' shinyApp(ui, server)
#'
#' @export
chat_ui <- function(
  id,
  ...,
  messages = NULL,
  placeholder = "Enter a message...",
  width = "min(680px, 100%)",
  height = "auto",
  fill = TRUE,
  icon_assistant = NULL
) {
  attrs <- rlang::list2(...)
  if (!all(nzchar(rlang::names2(attrs)))) {
    rlang::abort("All arguments in ... must be named.")
  }

  message_tags <- lapply(messages, function(x) {
    role <- "assistant"
    content <- x
    if (is.list(x) && ("content" %in% names(x))) {
      content <- x[["content"]]
      role <- x[["role"]] %||% role
    }

    # `content` is most likely a string, so avoid overhead in that case
    # (it's also important that we *don't escape HTML* here).
    if (is.character(content)) {
      ui <- list(html = paste(content, collapse = "\n"))
    } else {
      ui <- with_current_theme(htmltools::renderTags(content))
    }

    tag(
      "shiny-chat-message",
      rlang::list2(
        `data-role` = role,
        content = ui[["html"]],
        icon = if (!is.null(icon_assistant)) as.character(icon_assistant),
        ui[["dependencies"]],
      )
    )
  })

  res <- tag(
    "shiny-chat-container",
    rlang::list2(
      id = id,
      style = css(
        width = width,
        height = height
      ),
      placeholder = placeholder,
      fill = if (isTRUE(fill)) NA else NULL,
      # Also include icon on the parent so that when messages are dynamically added,
      # we know the default icon has changed
      `icon-assistant` = if (!is.null(icon_assistant)) {
        as.character(icon_assistant)
      },
      ...,
      tag("shiny-chat-messages", message_tags),
      tag(
        "shiny-chat-input",
        list(id = paste0(id, "_user_input"), placeholder = placeholder)
      ),
      chat_deps(),
      htmltools::findDependencies(icon_assistant)
    )
  )

  if (isTRUE(fill)) {
    res <- bslib::as_fill_carrier(res)
  }

  tag_require(res, version = 5, caller = "chat_ui")
}

#' Clear all messages from a chat control
#'
#' @param id The ID of the chat element
#' @param session The Shiny session object
#'
#' @export
#' @examplesIf interactive()
#'
#' library(shiny)
#' library(bslib)
#'
#' ui <- page_fillable(
#'   chat_ui("chat", fill = TRUE),
#'   actionButton("clear", "Clear chat")
#' )
#'
#' server <- function(input, output, session) {
#'   observeEvent(input$clear, {
#'     chat_clear("chat")
#'   })
#'
#'   observeEvent(input$chat_user_input, {
#'     response <- paste0("You said: ", input$chat_user_input)
#'     chat_append("chat", response)
#'   })
#' }
#'
#' shinyApp(ui, server)
chat_clear <- function(id, session = getDefaultReactiveDomain()) {
  check_active_session(session)

  session$sendCustomMessage(
    "shinyChatMessage",
    list(
      id = resolve_id(id, session),
      handler = "shiny-chat-clear-messages",
      obj = NULL
    )
  )
}


#' Update the user input of a chat control
#'
#' @param id The ID of the chat element
#' @param ... Currently unused, but reserved for future use.
#' @param value The value to set the user input to. If `NULL`, the input will not be updated.
#' @param placeholder The placeholder text for the user input
#' @param submit Whether to automatically submit the text for the user. Requires `value`.
#' @param focus Whether to move focus to the input element. Requires `value`.
#' @param session The Shiny session object
#'
#' @export
#' @examplesIf interactive()
#' library(shiny)
#' library(bslib)
#' library(shinychat)
#'
#' ui <- page_fillable(
#'   chat_ui("chat"),
#'   layout_columns(
#'     fill = FALSE,
#'     actionButton("update_placeholder", "Update placeholder"),
#'     actionButton("update_value", "Update user input")
#'   )
#' )
#'
#' server <- function(input, output, session) {
#'   observeEvent(input$update_placeholder, {
#'     update_chat_user_input("chat", placeholder = "New placeholder text")
#'   })
#'
#'   observeEvent(input$update_value, {
#'     update_chat_user_input("chat", value = "New user input", focus = TRUE)
#'   })
#'
#'   observeEvent(input$chat_user_input, {
#'     response <- paste0("You said: ", input$chat_user_input)
#'     chat_append("chat", response)
#'   })
#' }
#'
#' shinyApp(ui, server)

update_chat_user_input <- function(
  id,
  ...,
  value = NULL,
  placeholder = NULL,
  submit = FALSE,
  focus = FALSE,
  session = getDefaultReactiveDomain()
) {
  rlang::check_dots_empty()
  check_active_session(session)

  if (is.null(value) && (submit || focus)) {
    rlang::abort(
      "An input `value` must be provided when `submit` or `focus` are `TRUE`."
    )
  }

  vals <- drop_nulls(
    list(
      value = value,
      placeholder = placeholder,
      submit = submit,
      focus = focus
    )
  )

  session$sendCustomMessage(
    "shinyChatMessage",
    list(
      id = resolve_id(id, session),
      handler = "shiny-chat-update-user-input",
      obj = vals
    )
  )
}
