test_that("resolve_max_attachment_size honors env var and default", {
  old <- Sys.getenv("SHINYCHAT_MAX_ATTACHMENT_SIZE", unset = NA)
  on.exit({
    if (is.na(old)) {
      Sys.unsetenv("SHINYCHAT_MAX_ATTACHMENT_SIZE")
    } else {
      Sys.setenv(SHINYCHAT_MAX_ATTACHMENT_SIZE = old)
    }
  })
  Sys.setenv(SHINYCHAT_MAX_ATTACHMENT_SIZE = "2000000")
  expect_equal(resolve_max_attachment_size(), 2000000)
  Sys.unsetenv("SHINYCHAT_MAX_ATTACHMENT_SIZE")
  expect_equal(resolve_max_attachment_size(), 30L * 1024L * 1024L)
})

test_that("attachment_types loads the shipped JSON manifest", {
  types <- attachment_types()
  expect_true("application/pdf" %in% types$supported)
  expect_equal(types$ext_map[["pdf"]], "application/pdf")
  expect_true("text/plain" %in% types$text)
})

test_that("resolve_max_attachment_size rejects negative values", {
  old <- Sys.getenv("SHINYCHAT_MAX_ATTACHMENT_SIZE", unset = NA)
  on.exit({
    if (is.na(old)) {
      Sys.unsetenv("SHINYCHAT_MAX_ATTACHMENT_SIZE")
    } else {
      Sys.setenv(SHINYCHAT_MAX_ATTACHMENT_SIZE = old)
    }
  })
  Sys.setenv(SHINYCHAT_MAX_ATTACHMENT_SIZE = "-1")
  expect_error(resolve_max_attachment_size(), "non-negative")
})

test_that("resolve_attachment_attrs handles bool, subset, and errors", {
  expect_equal(resolve_attachment_attrs(TRUE), list(allow = NA, accept = NULL))
  expect_equal(
    resolve_attachment_attrs(FALSE),
    list(allow = NULL, accept = NULL)
  )
  expect_equal(
    resolve_attachment_attrs("application/pdf"),
    list(allow = NA, accept = "application/pdf")
  )
  expect_equal(
    resolve_attachment_attrs(c("image/png", "application/pdf")),
    list(allow = NA, accept = "image/png,application/pdf")
  )
  expect_equal(
    resolve_attachment_attrs(character(0)),
    list(allow = NULL, accept = NULL)
  )
  expect_error(
    resolve_attachment_attrs("application/msword"),
    "unsupported MIME type"
  )
})

test_that("contents_from_attachments returns empty list for NULL/empty", {
  expect_equal(contents_from_attachments(NULL), list())
  expect_equal(contents_from_attachments(list()), list())
})

test_that("contents_from_attachments wraps text in a file-attachment tag", {
  md <- "# Title\n\nbody"
  b64 <- jsonlite::base64_enc(charToRaw(md))
  res <- contents_from_attachments(
    list(
      list(
        mime = "text/markdown",
        data_url = paste0("data:text/markdown;base64,", b64),
        name = "notes.md"
      )
    )
  )
  expect_length(res, 1)
  expect_identical(
    res[[1]],
    "<file-attachment name=\"notes.md\" type=\"text/markdown\">\n# Title\n\nbody\n</file-attachment>"
  )
})

test_that("contents_from_attachments escapes name/type attributes", {
  b64 <- jsonlite::base64_enc(charToRaw("x"))
  res <- contents_from_attachments(
    list(
      list(
        mime = "text/plain",
        data_url = paste0("data:text/plain;base64,", b64),
        name = "a\"&<b.txt"
      )
    )
  )
  expect_match(
    res[[1]],
    "name=\"a&quot;&amp;&lt;b.txt\"",
    fixed = TRUE
  )
})

test_that("contents_from_attachments replaces invalid UTF-8 bytes", {
  b64 <- jsonlite::base64_enc(as.raw(c(0xff, 0xfe, 0x20, 0x78)))
  res <- contents_from_attachments(
    list(
      list(
        mime = "text/plain",
        data_url = paste0("data:text/plain;base64,", b64),
        name = "weird.txt"
      )
    )
  )
  expect_match(res[[1]], "\uFFFD", fixed = TRUE)
})

test_that("contents_from_attachments drops NUL bytes in text", {
  b64 <- jsonlite::base64_enc(as.raw(c(0x41, 0x00, 0x42)))
  res <- contents_from_attachments(
    list(
      list(
        mime = "text/plain",
        data_url = paste0("data:text/plain;base64,", b64),
        name = "n.txt"
      )
    )
  )
  expect_match(res[[1]], "AB", fixed = TRUE)
})

test_that("contents_from_attachments falls back to 'file' for empty name", {
  b64 <- jsonlite::base64_enc(charToRaw("hi"))
  res <- contents_from_attachments(
    list(
      list(
        mime = "text/plain",
        data_url = paste0("data:text/plain;base64,", b64),
        name = ""
      )
    )
  )
  expect_match(res[[1]], "name=\"file\"", fixed = TRUE)
})

test_that("contents_from_attachments builds ellmer image/pdf content", {
  img <- contents_from_attachments(
    list(
      list(
        mime = "image/png",
        data_url = "data:image/png;base64,AAAA",
        name = "p.png"
      )
    )
  )[[1]]
  expect_true(S7::S7_inherits(img, ellmer::ContentImage))

  pdf_b64 <- jsonlite::base64_enc(charToRaw("%PDF-1.4 hello"))
  pdf <- contents_from_attachments(
    list(
      list(
        mime = "application/pdf",
        data_url = paste0("data:application/pdf;base64,", pdf_b64),
        name = "r.pdf"
      )
    )
  )[[1]]
  expect_true(S7::S7_inherits(pdf, ellmer::ContentPDF))
})

test_that("contents_from_attachments errors on unsupported type", {
  expect_error(
    contents_from_attachments(
      list(
        list(
          mime = "application/octet-stream",
          data_url = "data:application/octet-stream;base64,AAAA",
          name = "blob.bin"
        )
      )
    ),
    "Unsupported attachment type"
  )
})

test_that("user_input_contents builds a splat-ready, text-first content list", {
  png <- paste0(
    "data:image/png;base64,",
    jsonlite::base64_enc(as.raw(c(1, 2, 3)))
  )
  value <- list(
    text = "hello",
    attachments = list(list(mime = "image/png", data_url = png, name = "a.png"))
  )
  out <- user_input_contents(value)
  expect_length(out, 2)
  expect_identical(out[[1]], "hello")
  expect_true(S7::S7_inherits(out[[2]], ellmer::ContentImage))
})

test_that("user_input_contents drops empty text (attachment-only message)", {
  png <- paste0(
    "data:image/png;base64,",
    jsonlite::base64_enc(as.raw(c(1, 2, 3)))
  )
  value <- list(
    text = "",
    attachments = list(list(mime = "image/png", data_url = png, name = "a.png"))
  )
  out <- user_input_contents(value)
  expect_length(out, 1)
  expect_true(S7::S7_inherits(out[[1]], ellmer::ContentImage))
})

test_that("user_input_contents returns a bare string in disabled mode", {
  # Disabled uploads send the historical bare-string input; pass it through.
  expect_identical(user_input_contents("just text"), "just text")
})

test_that("user_input_contents wraps enabled text-only input in a list", {
  # Enabled uploads always send a {text, attachments} composite -> a list,
  # even with no attachments, so the contract is one predictable shape.
  expect_identical(
    user_input_contents(list(text = "just text", attachments = list())),
    list("just text")
  )
})

test_that("user_input_contents tolerates a missing attachments key", {
  expect_identical(user_input_contents(list(text = "hi")), list("hi"))
})

test_that("user_input_contents returns NULL for NULL value", {
  expect_null(user_input_contents(NULL))
})

test_that("user_input_contents rejects oversized attachment payloads", {
  old <- Sys.getenv("SHINYCHAT_MAX_ATTACHMENT_SIZE", unset = NA)
  on.exit({
    if (is.na(old)) {
      Sys.unsetenv("SHINYCHAT_MAX_ATTACHMENT_SIZE")
    } else {
      Sys.setenv(SHINYCHAT_MAX_ATTACHMENT_SIZE = old)
    }
  })
  Sys.setenv(SHINYCHAT_MAX_ATTACHMENT_SIZE = "3")

  value <- list(
    text = "hello",
    attachments = list(
      list(
        mime = "text/plain",
        data_url = "data:text/plain;base64,AQIDBA==",
        name = "x.txt",
        size = 1
      )
    )
  )

  expect_error(user_input_contents(value), "maximum attachment size")
})

test_that("chat_attachment creates correct structure from a PNG path", {
  path <- withr::local_tempfile(fileext = ".png")
  writeBin(as.raw(c(0x89, 0x50, 0x4e, 0x47)), path)
  att <- chat_attachment(path)
  expect_equal(att$mime, "image/png")
  expect_equal(att$name, basename(path))
  expect_true(startsWith(att$data_url, "data:image/png;base64,"))
  expect_equal(att$size, 4L)
})

test_that("chat_attachment accepts explicit mime and name", {
  path <- withr::local_tempfile(fileext = ".xyz")
  writeBin(charToRaw("hello"), path)
  att <- chat_attachment(path, mime = "text/plain", name = "custom.txt")
  expect_equal(att$mime, "text/plain")
  expect_equal(att$name, "custom.txt")
  expect_equal(att$size, 5L)
})

test_that("chat_attachment errors on unrecognised extension without mime", {
  path <- withr::local_tempfile(fileext = ".xyz")
  writeBin(charToRaw("data"), path)
  expect_error(chat_attachment(path), "MIME type")
})

test_that("chat_attachment errors on unsupported explicit mime", {
  path <- withr::local_tempfile(fileext = ".bin")
  writeBin(charToRaw("data"), path)
  expect_error(
    chat_attachment(path, mime = "application/zip"),
    "Unsupported MIME type"
  )
})

test_that("chat_attachment errors when file does not exist", {
  expect_error(chat_attachment("/nonexistent/file.png"))
})

test_that("chat_attachment rejects vector paths", {
  path1 <- withr::local_tempfile(fileext = ".txt")
  path2 <- withr::local_tempfile(fileext = ".txt")
  writeBin(charToRaw("one"), path1)
  writeBin(charToRaw("two"), path2)
  expect_error(chat_attachment(c(path1, path2)), "must be a single string")
})

test_that("chat_ui emits attachment attributes", {
  html_on <- as.character(chat_ui("chat", allow_attachments = TRUE))
  expect_match(html_on, "allow-attachments")
  expect_match(html_on, "max-attachment-size")

  html_subset <- as.character(
    chat_ui("chat", allow_attachments = "application/pdf")
  )
  expect_match(
    html_subset,
    "attachment-accept=\"application/pdf\"",
    fixed = TRUE
  )

  html_off <- as.character(chat_ui("chat", allow_attachments = FALSE))
  expect_false(grepl("allow-attachments", html_off))
  # max-attachment-size is emitted unconditionally (mirrors Python).
  expect_match(html_off, "max-attachment-size")
})

test_that("update_chat_user_input: submit=TRUE requires value", {
  expect_error(
    update_chat_user_input("chat", submit = TRUE),
    "value.*must be provided"
  )
})

test_that("update_chat_user_input: focus=TRUE requires value or attachments", {
  expect_error(
    update_chat_user_input("chat", focus = TRUE),
    "value.*or.*attachments"
  )
  att <- list(
    list(
      mime = "image/png",
      data_url = "data:image/png;base64,AA",
      name = "x.png",
      size = 2L
    )
  )
  expect_error(
    update_chat_user_input("chat", focus = TRUE, attachments = att),
    regexp = "session",
    ignore.case = TRUE
  )
})

test_that("update_chat_user_input: attachment_mode validates", {
  expect_error(
    update_chat_user_input(
      "chat",
      attachments = list(),
      attachment_mode = "bad"
    ),
    "attachment_mode"
  )
})
