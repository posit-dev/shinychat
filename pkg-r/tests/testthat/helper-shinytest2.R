skip_if_shinytest2_unavailable <- function() {
  testthat::skip_on_cran()
  testthat::skip_if_not_installed("shinytest2")
  testthat::skip_if_not_installed("chromote")

  chrome <- tryCatch(
    chromote::find_chrome(),
    error = function(...) NULL
  )
  if (
    is.null(chrome) ||
      length(chrome) == 0 ||
      is.na(chrome[[1]]) ||
      !file.exists(chrome[[1]])
  ) {
    testthat::skip("A Chrome or Chromium executable is required.")
  }
}
