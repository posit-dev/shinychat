Sys.setenv(SHINYTEST2_APP_DRIVER_TEST_ON_CRAN = "true")
library(shinytest2)

args <- commandArgs(trailingOnly = FALSE)
file_arg <- grep("^--file=", args, value = TRUE)
script_dir <- dirname(normalizePath(sub("^--file=", "", file_arg)))
app_dir <- script_dir
out_dir <- file.path(script_dir, "..", "..", "images", "tool-ui")
dir.create(out_dir, showWarnings = FALSE, recursive = TRUE)

states <- list(
  list(state = "basic-running", click = NULL),
  list(state = "basic-settled", click = ".shiny-chat-tool-group__row"),
  list(state = "basic-error", click = ".shiny-chat-tool-group__row"),
  list(state = "annotations-running", click = NULL),
  list(state = "annotations-settled", click = NULL),
  list(state = "result-fields", click = NULL),
  list(state = "intent", click = NULL),
  list(state = "rich-html", click = NULL),
  list(state = "rich-markdown", click = ".shiny-chat-tool-group__row")
)

only <- commandArgs(trailingOnly = TRUE)
if (length(only)) {
  states <- Filter(function(x) x$state %in% only, states)
}

app <- AppDriver$new(
  app_dir,
  name = "tool-ui-screenshots",
  width = 900,
  height = 700
)

cs <- app$get_chromote_session()

tool_row_js <- "!!document.querySelector('.shiny-chat-tool-group, .shiny-chat-tool-call-row')"
drilldown_open_js <- paste(
  "!!document.querySelector(",
  "'.shiny-chat-tool-call-row__detail:not([hidden]) .shiny-tool-card'",
  ")"
)

for (st in states) {
  message("State: ", st$state)
  cs$go_to(paste0(app$get_url(), "?state=", st$state), delay = 2)
  app$wait_for_js(tool_row_js, timeout = 20000)

  if (!is.null(st$click)) {
    app$click(selector = st$click)
    app$wait_for_js(drilldown_open_js, timeout = 5000)
    Sys.sleep(0.5)
  } else {
    Sys.sleep(0.5)
  }

  out_file <- file.path(out_dir, paste0(st$state, ".png"))
  cs$screenshot(out_file, selector = ".shiny-chat-messages-content", scale = 2)
}

app$stop()
message("Screenshots written to ", normalizePath(out_dir))
