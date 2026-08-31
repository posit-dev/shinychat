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
  rendered_segments <- list()
  dependencies <- list()
  for (segment in split_content_by_trust(content)) {
    if (segment$trusted) {
      # No session at UI-construction time; block deps use the static
      # serialization and also propagate as page-level dependencies.
      for (part in derive_island_parts(segment$content)) {
        if (inherits(part, "shinychat_island_block_part")) {
          block <- list(
            type = "html_block",
            version = 1L,
            content = part$html
          )
          if (length(part$deps) > 0) {
            block$html_deps <- serialize_html_deps_static(part$deps)
          }
          rendered_segments[[length(rendered_segments) + 1]] <- list(
            block = block
          )
        } else {
          rendered_segments[[length(rendered_segments) + 1]] <- list(
            text = part$html,
            trusted = TRUE
          )
        }
        dependencies <- c(dependencies, part$deps)
      }
    } else {
      rendered_segments[[length(rendered_segments) + 1]] <- list(
        text = as.character(segment$content),
        trusted = FALSE
      )
    }
  }

  # The fallback `content` attribute carries every segment's HTML so a
  # client that fails closed on the provenance array still shows the
  # content, escaped and untrusted.
  rendered_content <- paste0(
    vapply(
      rendered_segments,
      function(segment) {
        if ("text" %in% names(segment)) {
          as.character(segment$text)
        } else {
          as.character(segment$block$content)
        }
      },
      character(1)
    ),
    collapse = ""
  )
  # A block entry is never a trusted fallback: the fail-closed path must
  # not render fallback content as trusted.
  fallback_trusted <- length(rendered_segments) == 1 &&
    isTRUE(rendered_segments[[1]]$trusted)

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
        rendered_segments,
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
#'
#'   An item may also be an already-structured content block (a
#'   `shinychat_block` such as a `web_search`/`web_search_results`/`web_fetch`
#'   block of the kind ellmer content normalization produces for
#'   [chat_append()]). Each block is sent as one complete, append-only
#'   structured block message; the client validates, groups, and renders it.
#'   Only the block types the stream client supports are accepted —
#'   `html_block` and the `web_*` family; any other block type (e.g. a tool
#'   block, which the client would drop with a warning) raises an error.
#' @param operation The operation to perform on the markdown stream. The default,
#' `"replace"`, will replace the current content with the new content stream.
#' The other option, `"append"`, will append the new content stream to the
#' existing content.
#'
#' @param session The Shiny session object.
#'
#' @return A promise that resolves to the accumulated stream content as a
#'   single string (structured blocks contribute nothing to the string).
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

  # A coroutine that fails before its first await throws synchronously,
  # so wrap in tryCatch to convert it to a rejected promise.
  result <- tryCatch(
    markdown_stream_impl(id, stream, operation, session),
    error = function(cnd) promises::promise_reject(cnd)
  )
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

# Structured block types the client's markdown-stream wire supports.
# Mirrors `asStreamBlock` in js/src/markdown-stream/markdown-stream-entry.ts.
# Anything else is dropped by the client with a warning, so reject here.
STREAM_BLOCK_TYPES <- c(
  "html_block",
  "web_search",
  "web_search_results",
  "web_fetch"
)

markdown_stream_impl <- NULL
rlang::on_load(
  markdown_stream_impl <- coro::async(function(id, stream, operation, session) {
    # A message carries `content` XOR `block`. Blocks arrive complete and
    # append-only.
    send_stream_message <- function(...) {
      session$sendCustomMessage(
        "shinyMarkdownStreamMessage",
        rlang::list2(id = id, ...)
      )
    }
    send_content_message <- function(
      content,
      operation,
      html_deps,
      trusted,
      segment_start
    ) {
      send_stream_message(
        content = content,
        operation = operation,
        html_deps = html_deps,
        trusted = trusted,
        segment_start = segment_start
      )
    }
    send_block_message <- function(block, html_deps) {
      send_stream_message(
        operation = "append",
        html_deps = html_deps,
        trusted = TRUE,
        segment_start = TRUE,
        block = block
      )
    }

    if (operation == "replace") {
      send_content_message(
        "",
        "replace",
        list(),
        trusted = FALSE,
        segment_start = TRUE
      )
    }

    send_stream_message(isStreaming = TRUE)

    on.exit({
      send_stream_message(isStreaming = FALSE)
    })

    result <- ""
    for (msg in stream) {
      if (promises::is.promising(msg)) {
        msg <- await(msg)
      }
      if (coro::is_exhausted(msg)) {
        break
      }

      if (inherits(msg, "shinychat_block")) {
        # An already-structured block ships as one complete block message.
        # Reject unsupported block types rather than silently discarding.
        block_type <- msg$type
        if (!isTRUE(block_type %in% STREAM_BLOCK_TYPES)) {
          rlang::abort(paste0(
            "Unsupported structured block in a markdown stream: ",
            if (is.null(block_type)) "NULL" else sprintf("'%s'", block_type),
            ". `markdown_stream()` accepts only html_block and web_* blocks ",
            "(web_search, web_search_results, web_fetch); other block types ",
            "(e.g. tool blocks) are dropped by the client and so are ",
            "rejected here."
          ))
        }
        send_block_message(msg, list())
        next
      }

      segments <- split_content_by_trust(msg)
      composite <- !(is.character(msg) && !inherits(msg, "html")) ||
        length(segments) > 1
      for (index in seq_along(segments)) {
        segment <- segments[[index]]
        if (segment$trusted) {
          # Trusted content walks the shared island derivation.
          parts <- derive_island_parts(segment$content)
          # Aggregate the run's deps onto the first outbound envelope so
          # every dep loads before any part mounts.
          run_deps <- serialize_html_deps(
            unlist(lapply(parts, function(part) part$deps), recursive = FALSE),
            session
          )
          for (part_index in seq_along(parts)) {
            part <- parts[[part_index]]
            envelope_deps <- list()
            if (part_index == 1) {
              envelope_deps <- run_deps
            }
            result <- paste0(result, part$html)
            if (inherits(part, "shinychat_island_block_part")) {
              block <- new_html_block(part$html)
              if (length(part$deps) > 0) {
                attr(block, "shinychat_html_deps") <- part$deps
              }
              block <- process_block_deps(block, session)$block
              send_block_message(block, envelope_deps)
            } else {
              send_content_message(
                part$html,
                "append",
                envelope_deps,
                trusted = TRUE,
                segment_start = TRUE
              )
            }
          }
        } else {
          text <- as.character(segment$content)
          result <- paste0(result, text)
          send_content_message(
            text,
            "append",
            list(),
            trusted = FALSE,
            segment_start = composite || index > 1
          )
        }
      }
    }

    result
  })
)
