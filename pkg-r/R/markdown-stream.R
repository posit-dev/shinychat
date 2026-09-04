#' Create a UI element for a markdown stream.
#'
#' @description
#' Creates a UI element for a [markdown_stream()]. A markdown stream can be
#' useful for displaying generative AI responses (outside of a chat interface),
#' streaming logs, or other use cases where chunks of content are generated
#' over time.
#'
#' @param id A unique identifier for this markdown stream.
#' @param ... Extra HTML attributes to include on the chat element
#' @param content A string of content to display before any streaming occurs.
#'   When `content_type` is Markdown or HTML, it may also be UI element(s) such
#'   as input and output bindings.
#' @param content_type The content type. Default is `"markdown"` (specifically,
#'   CommonMark). Supported content types include:
#'       * `"markdown"`: markdown text, specifically CommonMark
#'       * `"html"`: for rendering HTML content.
#'       * `"text"`: for plain text.
#' @param auto_scroll Whether to automatically scroll to the bottom of a
#'   scrollable container when new content is added. Default is True.
#' @param width The width of the UI element.
#' @param height The height of the UI element.
#'
#' @return A shiny tag object.
#'
#' @export
#' @seealso [markdown_stream()]
#'
output_markdown_stream <- function(
  id,
  ...,
  content = "",
  content_type = "markdown",
  auto_scroll = TRUE,
  width = "min(680px, 100%)",
  height = "auto"
) {
  segments <- lapply(split_content_by_trust(content), function(segment) {
    if (segment$trusted) {
      ui <- with_current_theme({
        htmltools::renderTags(pre_process_ui(segment$content))
      })
    } else {
      ui <- list(
        html = as.character(segment$content),
        dependencies = list()
      )
    }
    list(
      text = ui[["html"]],
      trusted = segment$trusted,
      dependencies = ui[["dependencies"]]
    )
  })
  rendered_content <- paste0(
    vapply(segments, `[[`, character(1), "text"),
    collapse = ""
  )
  dependencies <- unlist(
    lapply(segments, `[[`, "dependencies"),
    recursive = FALSE
  )
  fallback_trusted <- length(segments) == 1 && isTRUE(segments[[1]]$trusted)
  encoded_segments <- lapply(segments, function(segment) {
    list(text = segment$text, trusted = segment$trusted)
  })

  htmltools::tag(
    "shiny-markdown-stream",
    rlang::list2(
      id = id,
      style = css(
        width = width,
        height = height,
        margin = "0 auto"
      ),
      content = rendered_content,
      "content-type" = content_type,
      "content-segments" = jsonlite::toJSON(
        encoded_segments,
        auto_unbox = TRUE
      ),
      "content-trusted" = if (fallback_trusted) "true" else "false",
      "auto-scroll" = if (auto_scroll) "" else NULL,
      ...,
      dependencies,
      shinychat_deps()
    )
  )
}

#' Stream markdown content
#'
#' @description
#' Streams markdown content into a [output_markdown_stream()] UI element.  A
#' markdown stream can be useful for displaying generative AI responses (outside
#' of a chat interface), streaming logs, or other use cases where chunks of
#' content are generated over time.
#'
#' @param id The ID of the markdown stream to stream content to.
#' @param content_stream A string generator (e.g., [coro::generator()] or
#' [coro::async_generator()]), a string promise (e.g., [promises::promise()]),
#' or a string promise generator.
#' @param operation The operation to perform on the markdown stream. The default,
#' `"replace"`, will replace the current content with the new content stream.
#' The other option, `"append"`, will append the new content stream to the
#' existing content.
#'
#' @param session The Shiny session object.
#'
#' @return NULL
#'
#' @export
#' @examplesIf interactive()
#'
#' library(shiny)
#' library(coro)
#' library(bslib)
#' library(shinychat)
#'
#' # Define a generator that yields a random response
#' # (imagine this is a more sophisticated AI generator)
#' random_response_generator <- async_generator(function() {
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
#'   actionButton("generate", "Generate response"),
#'   output_markdown_stream("stream")
#' )
#'
#' server <- function(input, output, session) {
#'   observeEvent(input$generate, {
#'     markdown_stream("stream", random_response_generator())
#'   })
#' }
#'
#' shinyApp(ui, server)
markdown_stream <- function(
  id,
  content_stream,
  operation = c("replace", "append"),
  session = getDefaultReactiveDomain()
) {
  stream <- as_generator(content_stream)

  operation <- match.arg(operation)

  result <- markdown_stream_impl(id, stream, operation, session)
  result <- chat_update_bookmark(id, result, session = session)

  # Handle erroneous result...
  promises::catch(result, function(reason) {
    shiny::showNotification(
      sprintf(
        "Error in markdown_stream('%s'): %s",
        id,
        conditionMessage(reason)
      ),
      type = "error",
      duration = NULL,
      closeButton = TRUE
    )
  })
  # ...but also return it, so the caller can also handle it if they want. Note
  # that we're not returning the result of `promises::catch`; we want to return
  # a rejected promise (so the caller can see the error) that was already
  # handled (so there's no "unhandled promise error" warning if the caller
  # chooses not to do anything with it).
  result
}

markdown_stream_impl <- NULL
rlang::on_load(
  markdown_stream_impl <- coro::async(function(id, stream, operation, session) {
    send_stream_message <- function(...) {
      session$sendCustomMessage(
        "shinyMarkdownStreamMessage",
        rlang::list2(id = id, ...)
      )
    }

    if (operation == "replace") {
      send_stream_message(
        content = "",
        operation = "replace",
        trusted = FALSE,
        segment_start = TRUE
      )
    }

    send_stream_message(isStreaming = TRUE)

    on.exit({
      send_stream_message(isStreaming = FALSE)
    })

    for (msg in stream) {
      if (promises::is.promising(msg)) {
        msg <- await(msg)
      }
      if (coro::is_exhausted(msg)) {
        break
      }

      segments <- split_content_by_trust(msg)
      composite <- !(is.character(msg) && !inherits(msg, "html")) ||
        length(segments) > 1
      for (index in seq_along(segments)) {
        segment <- segments[[index]]
        if (segment$trusted) {
          ui <- process_ui(pre_process_ui(segment$content), session)
        } else {
          ui <- list(html = as.character(segment$content), deps = "[]")
        }

        send_stream_message(
          content = ui[["html"]],
          operation = "append",
          html_deps = ui[["deps"]],
          trusted = segment$trusted,
          segment_start = composite || index > 1
        )
      }
    }

    invisible(NULL)
  })
)
