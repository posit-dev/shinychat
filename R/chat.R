# This is a stripped-down port of the ui.Chat feature in py-shiny. The main
# things it's missing are server-side state management, i.e. the py-shiny
# version will keep the list of messages for you, and will handle the
# trimming of the message history to fit within the context window; these
# are left for the caller to handle in the R version.

#' @importFrom htmltools tag css
#' @importFrom coro async
NULL

chat_deps <- function() {
  htmltools::htmlDependency(
    "shinychat",
    utils::packageVersion("shinychat"),
    package = "shinychat",
    src = "lib/shiny",
    script = list(
      list(src = "chat/chat.js", type = "module"),
      list(src = "markdown-stream/markdown-stream.js", type = "module"),
      list(src = "text-area/textarea-autoresize.js", type = "module")
    ),
    stylesheet = c(
      "chat/chat.css", 
      "markdown-stream/markdown-stream.css",
      "text-area/textarea-autoresize.css"
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
#'   message can be a string or a named list with `content` and `role` fields.
#' @param placeholder The placeholder text for the chat's user input field
#' @param width The CSS width of the chat element
#' @param height The CSS height of the chat element
#' @param fill Whether the chat element should try to vertically fill its
#'   container, if the container is
#'   [fillable](https://rstudio.github.io/bslib/articles/filling/index.html)
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
#'     # In a real app, this would call out to a chat model or API,
#'     # perhaps using the 'elmer' package.
#'     response <- paste0(
#'       "You said:\n\n",
#'       "<blockquote>",
#'       htmltools::htmlEscape(input$chat_user_input),
#'       "</blockquote>"
#'     )
#'     chat_append("chat", response)
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
    fill = TRUE) {

  attrs <- rlang::list2(...)
  if (!all(nzchar(rlang::names2(attrs)))) {
    rlang::abort("All arguments in ... must be named.")
  }

  message_tags <- lapply(messages, function(x) {
    if (is.character(x)) {
      x <- list(content = x, role = "assistant")
    } else if (is.list(x)) {
      if (!("content" %in% names(x))) {
        rlang::abort("Each message must have a 'content' key.")
      }
      if (!("role" %in% names(x))) {
        rlang::abort("Each message must have a 'role' key.")
      }
    } else {
      rlang::abort("Each message must be a string or a named list.")
    }

    if (isTRUE(x[["role"]] == "user")) {
      tag_name <- "shiny-user-message"
    } else {
      tag_name <- "shiny-chat-message"
    }

    tag(tag_name, list(content = x[["content"]]))
  })

  res <- tag("shiny-chat-container", rlang::list2(
    id = id,
    style = css(
      width = width,
      height = height
    ),
    placeholder = placeholder,
    fill = if (isTRUE(fill)) NA else NULL,
    ...,
    tag("shiny-chat-messages", message_tags),
    tag("shiny-chat-input", list(id=paste0(id, "_user_input"), placeholder=placeholder)),
    chat_deps()
  ))

  if (isTRUE(fill)) {
    res <- bslib::as_fill_carrier(res)
  }

  res
}

#' Append an assistant response (or user message) to a chat control
#'
#' @description
#' The `chat_append` function appends a message to an existing chat control. The
#' `response` can be a string, string generator, string promise, or string
#' promise generator (as returned by the 'elmer' package's `chat`, `stream`,
#' `chat_async`, and `stream_async` methods, respectively).
#' 
#' This function should be called from a Shiny app's server. It is generally
#' used to append the model's response to the chat, while user messages are
#' added to the chat UI automatically by the front-end. You'd only need to use
#' `chat_append(role="user")` if you are programmatically generating queries
#' from the server and sending them on behalf of the user, and want them to be
#' reflected in the UI.
#' 
#' # Error handling
#' 
#' If the `response` argument is a generator, promise, or promise generator, and
#' an error occurs while producing the message (e.g., an iteration in
#' `stream_async` fails), the promise returned by `chat_append` will reject with
#' the error. If the `chat_append` call is the last expression in a Shiny
#' observer, Shiny will see that the observer failed, and end the user session.
#' If you prefer to handle the error gracefully, use [promises::catch()] on the
#' promise returned by `chat_append`.
#' 
#' @param id The ID of the chat element
#' @param response The message or message stream to append to the chat element
#' @param role The role of the message (either "assistant" or "user"). Defaults
#'   to "assistant".
#' @param session The Shiny session object
#' @returns Returns a promise. This promise resolves when the message has been
#'   successfully sent to the client; note that it does not guarantee that the
#'   message was actually received or rendered by the client. The promise
#'   rejects if an error occurs while processing the response (see the "Error
#'   handling" section).
#'
#' @examplesIf interactive()
#' library(shiny)
#' library(coro)
#' library(bslib)
#' library(shinychat)
#' 
#' # Dumbest chatbot in the world: ignores user input and chooses
#' # a random, vague response.
#' fake_chatbot <- async_generator(function(input) {
#'   responses <- c(
#'     "What does that suggest to you?",
#'     "I see.",
#'     "I'm not sure I understand you fully.",
#'     "What do you think?",
#'     "Can you elaborate on that?",
#'     "Interesting question! Let's examine thi... **See more**"
#'   )
#' 
#'   await(async_sleep(1))
#'   for (chunk in strsplit(sample(responses, 1), "")[[1]]) {
#'     yield(chunk)
#'     await(async_sleep(0.02))
#'   }
#' })
#' 
#' ui <- page_fillable(
#'   chat_ui("chat", fill = TRUE)
#' )
#' 
#' server <- function(input, output, session) {
#'   observeEvent(input$chat_user_input, {
#'     response <- fake_chatbot(input$chat_user_input)
#'     chat_append("chat", response)
#'   })
#' }
#' 
#' shinyApp(ui, server)
#' 
#' @export
chat_append <- function(id, response, role = c("assistant", "user"), session = getDefaultReactiveDomain()) {
  role <- match.arg(role)
  if (is.character(response)) {
    # string => generator
    stream <- coro::gen(yield(response))
  } else if (promises::is.promising(response)) {
    # promise => async generator
    stream <- coro::gen(yield(response))
  } else if (inherits(response, "coro_generator_instance")) {
    # Already a generator (sync or async)
    stream <- response
  } else {
    rlang::abort("Unexpected message type; chat_append() expects a string, a string generator, a string promise, or a string promise generator")
  }
  chat_append_stream(id, stream, role = role, session = session)
}

#' Low-level function to append a message to a chat control
#'
#' For advanced users who want to control the message chunking behavior. Most
#' users should use [chat_append()] instead.
#'
#' @param id The ID of the chat element
#' @param msg The message to append. Should be a named list with `role` and
#'   `content` fields. The `role` field should be either "user" or "assistant".
#'   The `content` field should be a string containing the message content, in
#'   Markdown format.
#' @param chunk Whether `msg` is just a chunk of a message, and if so, what
#'   type. If `FALSE`, then `msg` is a complete message. If `"start"`, then
#'   `msg` is the first chunk of a multi-chunk message. If `"end"`, then `msg`
#'   is the last chunk of a multi-chunk message. If `TRUE`, then `msg` is an
#'   intermediate chunk of a multi-chunk message. Default is `FALSE`.
#' @param operation The operation to perform on the message. If `"append"`,
#'   then the new content is appended to the existing message content. If
#'   `"replace"`, then the existing message content is replaced by the new
#'   content. Ignored if `chunk` is `FALSE`.
#' @param session The Shiny session object
#'
#' @returns Returns nothing (\code{invisible(NULL)}).
#'
#' @importFrom shiny getDefaultReactiveDomain
#' 
#' @examplesIf interactive()
#' library(shiny)
#' library(coro)
#' library(bslib)
#' library(shinychat)
#' 
#' # Dumbest chatbot in the world: ignores user input and chooses
#' # a random, vague response.
#' fake_chatbot <- async_generator(function(id, input) {
#'   responses <- c(
#'     "What does that suggest to you?",
#'     "I see.",
#'     "I'm not sure I understand you fully.",
#'     "What do you think?",
#'     "Can you elaborate on that?",
#'     "Interesting question! Let's examine thi... **See more**"
#'   )
#' 
#'   # Use low-level chat_append_message() to temporarily set a progress message
#'   chat_append_message(id, list(role = "assistant", content = "_Thinking..._ "))
#'   await(async_sleep(1))
#'   # Clear the progress message
#'   chat_append_message(id, list(role = "assistant", content = ""), operation = "replace")
#'
#'   for (chunk in strsplit(sample(responses, 1), "")[[1]]) {
#'     yield(chunk)
#'     await(async_sleep(0.02))
#'   }
#' })
#' 
#' ui <- page_fillable(
#'   chat_ui("chat", fill = TRUE)
#' )
#' 
#' server <- function(input, output, session) {
#'   observeEvent(input$chat_user_input, {
#'     response <- fake_chatbot("chat", input$chat_user_input)
#'     chat_append("chat", response)
#'   })
#' }
#' 
#' shinyApp(ui, server)
#' 
#' @export
chat_append_message <- function(id, msg, chunk = TRUE, operation = c("append", "replace"), session = getDefaultReactiveDomain()) {
  if (!is.list(msg)) {
    rlang::abort("msg must be a named list with 'role' and 'content' fields")
  }
  if (!isTRUE(msg[["role"]] %in% c("user", "assistant"))) {
    warning("Invalid role argument; must be 'user' or 'assistant'")
    return(invisible(NULL))
  }

  if (!isFALSE(chunk)) {
    msg_type <- "shiny-chat-append-message-chunk"
    if (chunk == "start") {
      chunk_type <- "message_start"
    } else if (chunk == "end") {
      chunk_type <- "message_end"
    } else if (isTRUE(chunk)) {
      chunk_type <- NULL
    } else {
      rlang::abort("Invalid chunk argument")
    }
  } else {
    msg_type <- "shiny-chat-append-message"
    chunk_type <- NULL
  }

  if (identical(class(msg[["content"]]), "character")) {
    content_type <- "markdown"
  } else {
    content_type <- "html"
  }

  operation <- match.arg(operation)
  if (identical(operation, "replace")) {
    operation <- NULL
  }

  msg <- list(
    content = msg[["content"]],
    role = msg[["role"]],
    content_type = content_type,
    chunk_type = chunk_type,
    operation = operation
  )

  session$sendCustomMessage("shinyChatMessage", list(
    id = id,
    handler = msg_type,
    obj = msg
  ))

  invisible(NULL)
}

chat_append_stream <- function(id, stream, role = "assistant", session = getDefaultReactiveDomain()) {
  result <- chat_append_stream_impl(id, stream, role, session)
  # Handle erroneous result...
  promises::catch(result, function(reason) {
    chat_append_message(
      id,
      list(
        role = role,
        content = paste0("\n\n**An error occurred:** ", conditionMessage(reason))
      ),
      chunk = "end",
      operation = "append",
      session = session
    )
  })
  # ...but also return it, so the caller can also handle it if they want. Note
  # that we're not returning the result of `promises::catch`; we want to return
  # a rejected promise (so the caller can see the error) that was already
  # handled (so there's no "unhandled promise error" warning if the caller
  # chooses not to do anything with it).
  result
}

utils:::globalVariables(c("generator_env", "exits", "yield"))

chat_append_stream_impl <- NULL
rlang::on_load(chat_append_stream_impl <- coro::async(function(id, stream, role = "assistant", session = shiny::getDefaultReactiveDomain()) {
  chat_append_message(id, list(role = role, content = ""), chunk = "start", session = session)
  for (msg in stream) {
    if (promises::is.promising(msg)) {
      msg <- await(msg)
    }
    if (coro::is_exhausted(msg)) {
      break
    }
    chat_append_message(id, list(role = role, content = msg), chunk = TRUE, operation = "append", session = session)
  }
  chat_append_message(id, list(role = role, content = ""), chunk = "end", operation = "append", session = session)
}))
