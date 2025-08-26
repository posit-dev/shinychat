#' Append an assistant response (or user message) to a chat control
#'
#' @description
#' The `chat_append` function appends a message to an existing [chat_ui()]. The
#' `response` can be a string, string generator, string promise, or string
#' promise generator (as returned by the 'ellmer' package's `chat`, `stream`,
#' `chat_async`, and `stream_async` methods, respectively).
#'
#' This function should be called from a Shiny app's server. It is generally
#' used to append the client's response to the chat, while user messages are
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
#' @param response The message or message stream to append to the chat element.
#'   The actual message content can one of the following:
#'
#'   * A string, which is interpreted as markdown and rendered to HTML on
#'     the client.
#'     * To prevent interpreting as markdown, mark the string as
#'       [htmltools::HTML()].
#'   * A UI element.
#'     * This includes [htmltools::tagList()], which take UI elements
#'       (including strings) as children. In this case, strings are still
#'       interpreted as markdown as long as they're not inside HTML.
#'
#' @param role The role of the message (either "assistant" or "user"). Defaults
#'   to "assistant".
#' @param icon An optional icon to display next to the message, currently only
#'   used for assistant messages. The icon can be any HTML element (e.g., an
#'   [htmltools::img()] tag) or a string of HTML.
#' @param session The Shiny session object
#'
#' @returns Returns a promise that resolves to the contents of the stream, or an
#'   error. This promise resolves when the message has been successfully sent to
#'   the client; note that it does not guarantee that the message was actually
#'   received or rendered by the client. The promise rejects if an error occurs
#'   while processing the response (see the "Error handling" section).
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
chat_append <- function(
  id,
  response,
  role = "assistant",
  icon = NULL,
  session = getDefaultReactiveDomain()
) {
  check_active_session(session)
  if (!is_string(role)) {
    cli::cli_abort(
      "{.var role} must be a string, e.g. {.or {c('user', 'assistant')}}."
    )
  }

  stream <- as_generator(response)
  chat_append_stream(id, stream, role = role, icon = icon, session = session)
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
#' @param icon An optional icon to display next to the message, currently only
#'   used for assistant messages. The icon can be any HTML element (e.g.,
#'   [htmltools::img()] tag) or a string of HTML.
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
chat_append_message <- function(
  id,
  msg,
  chunk = TRUE,
  operation = c("append", "replace"),
  icon = NULL,
  session = getDefaultReactiveDomain()
) {
  check_active_session(session)

  if (!is.list(msg)) {
    rlang::abort("`msg` must be a named list with 'role' and 'content' fields")
  }
  if (!is_string(msg[["role"]])) {
    cli::cli_warn(
      "Invalid message role {.var msg[['role']]}. Must be a string, e.g. {.or {c('user', 'assistant')}}."
    )
    return(invisible(NULL))
  }

  if (isFALSE(chunk)) {
    msg <- chat_event_message(
      id,
      role = msg[["role"]],
      content = msg[["content"]],
      icon = icon,
      session = session
    )

    return(invisible(msg))
  }

  if (identical(chunk, "start")) {
    msg <- chat_event_message_start(
      id,
      role = msg[["role"]],
      content_type = if (msg[["role"]] == "assistant") {
        "markdown"
      } else {
        "semi-markdown"
      },
      icon = icon,
      session = session
    )
  } else if (identical(chunk, "end")) {
    msg <- chat_event_message_end(
      id,
      session = session
    )
  } else if (isTRUE(chunk)) {
    msg <- chat_event_message_append(
      id,
      content = msg[["content"]],
      operation = operation,
      session = session
    )
  } else {
    cli::cli_abort(
      "{.var chunk} must be {.code FALSE}, {.code TRUE}, {.or {c('start', 'end')}}."
    )
  }

  invisible(msg)
}

chat_event_message <- function(
  id,
  role = "assistant",
  content,
  icon = NULL,
  session = getDefaultReactiveDomain()
) {
  msg <- list2(
    role = role,
    !!!chat_event_payload_content(content),
    icon = if (!is.null(icon)) as.character(icon)
  )

  session$sendCustomMessage(
    "shinyChatMessage",
    list(
      id = resolve_id(id, session),
      handler = "shiny-chat-message",
      obj = msg
    )
  )

  invisible(msg)
}

chat_event_message_start <- function(
  id,
  role,
  content_type = "html",
  icon = NULL,
  stream_id = NULL,
  session = getDefaultReactiveDomain()
) {
  stream_id <- stream_id %||% stream_id_new()
  the$active_streams <- c(the$active_streams, stream_id)

  msg <- list(
    streamId = stream_id,
    role = role,
    contentType = content_type,
    icon = if (!is.null(icon)) as.character(icon)
  )

  session$sendCustomMessage(
    "shinyChatMessage",
    list(
      id = resolve_id(id, session),
      handler = "shiny-chat-message-start",
      obj = msg
    )
  )

  invisible(msg)
}

the$active_streams <- c()

stream_id_new <- function() {
  stream_id <- asNamespace("shiny")$p_randomInt(1e8, 1e9 - 1L)
  stream_id <- as.character(as.hexmode(stream_id))
  paste0("stream-", stream_id)
}

active_stream_id_get <- function() {
  if (length(the$active_streams) == 0) {
    cli::cli_abort("No active streams")
  }
  the$active_streams[[1]]
}

active_stream_id_remove <- function(id) {
  the$active_streams <- setdiff(the$active_streams, id)
}

chat_event_message_append <- function(
  id,
  content,
  operation = c("append", "replace"),
  stream_id = NULL,
  session = getDefaultReactiveDomain()
) {
  stream_id <- stream_id %||% active_stream_id_get()
  operation <- arg_match(operation)

  msg <- list2(
    streamId = stream_id,
    operation = operation,
    !!!chat_event_payload_content(content, session)
  )

  # Content type was already set in the start message
  msg$content_type <- NULL

  session$sendCustomMessage(
    "shinyChatMessage",
    list(
      id = resolve_id(id, session),
      handler = "shiny-chat-message-append",
      obj = msg
    )
  )

  invisible(msg)
}

chat_event_message_end <- function(
  id,
  stream_id = NULL,
  session = getDefaultReactiveDomain()
) {
  stream_id <- stream_id %||% active_stream_id_get()
  active_stream_id_remove(stream_id)

  msg <- list(streamId = stream_id)

  session$sendCustomMessage(
    "shinyChatMessage",
    list(
      id = resolve_id(id, session),
      handler = "shiny-chat-message-end",
      obj = msg
    )
  )

  invisible(msg)
}

chat_event_payload_content <- function(
  content,
  session = getDefaultReactiveDomain()
) {
  content <- content
  is_html <- inherits(
    content,
    c(
      "shiny.tag",
      "shiny.tag.list",
      "html",
      "htmlwidget",
      "shinychat_tool_card"
    )
  )
  content_type <- if (is_html) "html" else "markdown"

  if (is.character(content)) {
    # content is most likely a string, so avoid overhead in that case
    ui <- list(html = content, deps = "[]")
  } else {
    # process_ui() does *not* render markdown->HTML, but it does:
    # 1. Extract and register HTMLdependency()s with the session.
    # 2. Returns a HTML string representation of the TagChild
    #    (i.e., `div()` -> `"<div>"`).
    ui <- process_ui(content, session)
  }

  msg_content <- ui[["html"]]
  if (is_html) {
    # Code blocks with `{=html}` infostrings are rendered as-is by a custom
    # rendering method in markdown-stream.ts
    msg_content <- sprintf(
      "\n\n````````{=html}\n%s\n````````\n\n",
      msg_content
    )
  }

  list(
    content = msg_content,
    contentType = content_type,
    html_deps = ui[["deps"]]
  )
}

chat_append_stream <- function(
  id,
  stream,
  role = "assistant",
  icon = NULL,
  session = getDefaultReactiveDomain()
) {
  result <- chat_append_stream_impl(id, stream, role, icon, session)
  result <- chat_update_bookmark(id, result, session = session)
  # Handle erroneous result...
  result <- promises::catch(result, function(reason) {
    # ...but rethrow the error as a silent error, so the caller can also handle
    # it if they want, but it won't bring down the app.
    class(reason) <- c("shiny.silent.error", class(reason))
    cnd_signal(reason)
  })

  promises::catch(result, function(reason) {
    chat_append_message(
      id,
      list(
        role = role,
        content = sanitized_chat_error(reason)
      ),
      chunk = "end",
      operation = "append",
      session = session
    )
    rlang::warn(
      sprintf(
        "ERROR: An error occurred in `chat_append_stream(id=\"%s\")`",
        session$ns(id)
      ),
      parent = reason
    )
  })

  # Note that we're not returning the result of `promises::catch()`, because we
  # want to return a rejected promise so the caller can see the error. But we
  # use the `catch()` both to make the error visible to the user *and* to ensure
  # there's no "unhandled promise error" warning if the caller chooses not to do
  # anything with it.
  result
}

chat_event_enable_input <- function(id, session = getDefaultReactiveDomain()) {
  session$sendCustomMessage(
    "shinyChatMessage",
    list(
      id = resolve_id(id, session),
      handler = "shiny-chat-input-enable",
      obj = NULL
    )
  )

  invisible(NULL)
}

utils:::globalVariables(c("generator_env", "exits", "yield"))

chat_append_stream_impl <- NULL
rlang::on_load(
  chat_append_stream_impl <- coro::async(function(
    id,
    stream,
    role = "assistant",
    icon = NULL,
    session = shiny::getDefaultReactiveDomain()
  ) {
    chat_append_ <- function(content, chunk = TRUE, ...) {
      chat_append_message(
        id,
        msg = list(role = role, content = content),
        operation = "append",
        chunk = chunk,
        session = session,
        ...
      )
    }
    on.exit(chat_event_enable_input(id, session), add = TRUE)

    res <- fastmap::fastqueue(200)

    do_start_stream <- TRUE
    this_stream_stage <- stream_stage_state_machine()

    for (msg in stream) {
      if (promises::is.promising(msg)) {
        msg <- await(msg)
      }
      if (coro::is_exhausted(msg)) {
        break
      }

      if (do_start_stream) {
        chat_append_("", chunk = "start", icon = icon)
        do_start_stream <- FALSE
      }

      res$add(msg)

      if (identical(this_stream_stage(msg), "reset")) {
        chat_append_("", chunk = "end")
        chat_append_("", chunk = "start")
      }

      if (S7::S7_inherits(msg, ellmer::ContentToolResult)) {
        if (!is.null(msg@request)) {
          session$sendCustomMessage("shiny-tool-request-hide", msg@request@id)
        }
      }

      if (S7::S7_inherits(msg, ellmer::Content)) {
        msg <- contents_shinychat(msg)
      }

      chat_append_(msg)
    }

    chat_append_("", chunk = "end")

    res <- res$as_list()
    if (every(res, is.character)) {
      paste(unlist(res), collapse = "")
    } else {
      res
    }
  })
)

stream_stage_state_machine <- function() {
  stage <- "start"
  last_was_tool <- FALSE

  # not_tool -> tool || "reset"
  # tool -> tool || "pending"
  # tool -> not_tool || "reset"
  # not_tool -> not_tool || "stream"

  # TODO: {ellmer} could emit a special "stream end" object inside the tool loop
  # between internal user/assistant turns, and then we wouldn't need to manually
  # track state here.

  function(x) {
    # Avoid state-machine overhead when ellmer is emitting plain text
    if (identical(stage, "always_stream")) {
      return("stream")
    }

    if (is.character(x)) {
      stage <<- "always_stream"
      return("stream")
    }

    stage_last <- stage

    if (is_tool_content(x)) {
      stage <<- if (last_was_tool || stage == "start") "pending" else "reset"
      last_was_tool <<- TRUE
    } else {
      stage <<- if (stage == "pending") "reset" else "stream"
      last_as_tool <<- FALSE
    }

    stage
  }
}

is_content_tool_request <- function(x) {
  S7::S7_inherits(x, ellmer::ContentToolRequest)
}

is_content_tool_result <- function(x) {
  S7::S7_inherits(x, ellmer::ContentToolResult)
}

is_tool_content <- function(x) {
  is_content_tool_request(x) || is_content_tool_result(x)
}
