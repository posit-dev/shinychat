# Helpers for user-uploaded chat attachments (images, PDFs, and text files).
# Public parameter name is `allow_attachments`; this module keeps attachment
# vocabulary throughout.

attachment_types <- local({
  cache <- NULL
  function() {
    if (is.null(cache)) {
      path <- system.file(
        "lib/shiny/attachment-types.json",
        package = "shinychat"
      )
      types <- jsonlite::fromJSON(path, simplifyVector = TRUE)
      text_exts <- types[["text_extensions"]]
      text <- unique(unname(text_exts))
      supported <- c(types[["image_types"]], types[["pdf_type"]], text)
      image_exts <- c(
        png = "image/png",
        jpg = "image/jpeg",
        jpeg = "image/jpeg",
        gif = "image/gif",
        webp = "image/webp"
      )
      ext_map <- c(
        image_exts,
        pdf = unname(types[["pdf_type"]]),
        text_exts
      )
      cache <<- list(text = text, supported = supported, ext_map = ext_map)
    }
    cache
  }
})

# Resolve the max combined attachment size (bytes) from the env var or default.
resolve_max_attachment_size <- function(default = 30L * 1024L * 1024L) {
  env <- Sys.getenv("SHINYCHAT_MAX_ATTACHMENT_SIZE", unset = "")
  size <- suppressWarnings(as.numeric(if (nzchar(env)) env else default))
  if (is.na(size)) {
    cli::cli_abort(
      "{.envvar SHINYCHAT_MAX_ATTACHMENT_SIZE} must be a number of bytes, got {.val {env}}."
    )
  }
  size
}

# Resolve `allow_attachments` into the allow/accept attribute pair.
# `allow` is NA (bare attribute) or NULL (omit); `accept` is a CSV or NULL.
resolve_attachment_attrs <- function(allow_attachments) {
  if (isTRUE(allow_attachments)) {
    return(list(allow = NA, accept = NULL))
  }
  if (isFALSE(allow_attachments)) {
    return(list(allow = NULL, accept = NULL))
  }
  if (is.character(allow_attachments)) {
    invalid <- setdiff(allow_attachments, attachment_types()$supported)
    if (length(invalid) > 0) {
      cli::cli_abort(
        c(
          "{.arg allow_attachments} contains unsupported MIME type{?s}: {.val {invalid}}.",
          i = "Supported types: {.val {attachment_types()$supported}}"
        )
      )
    }
    # An empty vector means "no types accepted" -> treat as disabled.
    if (length(allow_attachments) == 0) {
      return(list(allow = NULL, accept = NULL))
    }
    return(list(allow = NA, accept = paste(allow_attachments, collapse = ",")))
  }
  cli::cli_abort(
    "{.arg allow_attachments} must be {.code TRUE}, {.code FALSE}, or a character vector of MIME types."
  )
}

# Convert the `attachments` array from the composite `input$<id>_user_input`
# value (a list of lists, each with `type`, `dataUrl`, `name`) into a list of
# ellmer Content objects. Used by the `shinychat.userInput` input handler.
contents_from_attachments <- function(attachments) {
  if (is.null(attachments) || length(attachments) == 0) {
    return(list())
  }
  lapply(attachments, content_from_attachment)
}

content_from_attachment <- function(att) {
  mime <- att[["type"]]
  data_url <- att[["dataUrl"]]
  name <- att[["name"]] %||% ""

  if (startsWith(mime, "image/")) {
    return(ellmer::content_image_url(data_url))
  }
  if (identical(mime, "application/pdf")) {
    return(ellmer::content_pdf_url(data_url))
  }
  if (mime %in% attachment_types()$text) {
    # Returned as a plain string: ellmer coerces character `...` args to
    # ContentText, so no explicit content constructor is needed here.
    text <- decode_data_url_text(data_url)
    nm <- if (nzchar(name)) name else "file"
    return(
      sprintf(
        "<file-attachment name=\"%s\" type=\"%s\">\n%s\n</file-attachment>",
        htmltools::htmlEscape(nm, attribute = TRUE),
        htmltools::htmlEscape(mime, attribute = TRUE),
        text
      )
    )
  }
  cli::cli_abort("Unsupported attachment type: {.val {mime}}")
}


# Shape the value exposed on `input$<id>_user_input`. The wire shape encodes the
# upload mode, so the return type is predictable per mode:
#   * disabled -> a bare string (the historical string-valued input).
#   * enabled  -> a {text, attachments} list, always shaped into a splat-ready
#     list of ellmer Content (text first, then one content per attachment),
#     even when no files are attached.
# This is what the registered "shinychat.userInput" handler returns.
user_input_contents <- function(value) {
  if (is.null(value)) {
    return(NULL)
  }
  if (is.character(value)) {
    return(value)
  }
  text <- value[["text"]] %||% ""
  contents <- contents_from_attachments(value[["attachments"]])
  if (nzchar(text)) {
    contents <- c(list(text), contents)
  }
  contents
}

# Decode the base64 payload of a data URL to a UTF-8 string. R strings cannot
# hold embedded NUL, so NUL bytes are dropped (rawToChar would otherwise error);
# remaining invalid UTF-8 is replaced with U+FFFD, akin to Python's
# decode(errors="replace").
#' Create an attachment from a local file path
#'
#' Reads a file, base64-encodes its contents, and returns a list in the format
#' expected by the `attachments` argument of [update_chat_user_input()].
#'
#' @param path Path to the file. The file must exist.
#' @param mime MIME type of the file. When `NULL` (default), guessed from the
#'   file extension. Raises an error if the extension is unrecognised.
#' @param name Filename shown in the attachment chip. Defaults to
#'   `basename(path)`.
#'
#' @returns A list with elements `mime`, `name`, `size`, and `data_url`,
#'   ready to pass as an element of the `attachments` argument of
#'   [update_chat_user_input()].
#'
#' @export
chat_attachment <- function(path, mime = NULL, name = NULL) {
  path <- normalizePath(as.character(path), mustWork = TRUE)

  if (is.null(mime)) {
    ext <- tolower(tools::file_ext(path))
    mime <- attachment_types()$ext_map[[ext]]
    if (is.null(mime)) {
      cli::cli_abort(c(
        "Cannot determine MIME type for {.path {path}}.",
        "i" = "Specify the {.arg mime} argument explicitly."
      ))
    }
  }

  raw <- readBin(path, "raw", n = file.size(path))
  b64 <- base64enc::base64encode(raw)

  list(
    mime = mime,
    name = name %||% basename(path),
    size = length(raw),
    data_url = paste0("data:", mime, ";base64,", b64)
  )
}

decode_data_url_text <- function(data_url) {
  comma <- regexpr(",", data_url, fixed = TRUE)
  if (comma == -1L) {
    cli::cli_abort("Malformed data URL")
  }
  b64 <- substring(data_url, comma + 1L)
  bytes <- jsonlite::base64_dec(b64)
  bytes <- bytes[bytes != as.raw(0L)]
  iconv(rawToChar(bytes), from = "UTF-8", to = "UTF-8", sub = "\uFFFD")
}
