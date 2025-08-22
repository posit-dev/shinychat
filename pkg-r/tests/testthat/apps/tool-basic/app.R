library(shiny)
library(ellmer)
library(shinychat)

rlang::check_installed("ellmer", version = "0.3.0")

PROVIDER_MODEL = Sys.getenv("TEST_PROVIDER_MODEL", "openai/gpt-4.1-nano")

TOOL_OPTS <- list(
  async = as.logical(Sys.getenv("TEST_TOOL_ASYNC", "TRUE")),
  with_intent = as.logical(Sys.getenv("TEST_TOOL_WITH_INTENT", "TRUE")),
  with_title = as.logical(Sys.getenv("TEST_TOOL_WITH_TITLE", "TRUE")),
  with_icon = as.logical(Sys.getenv("TEST_TOOL_WITH_ICON", "TRUE"))
)

ui <- bslib::page_fillable(
  shinychat::chat_mod_ui(
    "chat",
    messages = list(list(
      role = "assistant",
      content = htmltools::HTML(
        '<span class="suggestion submit">In three separate but parallel tool calls list the files in apps, data, docs</span>

<span class="suggestion submit">Write some basic R code that demonstrates how to use the tidyverse.</span>

<span class="suggestion submit">Brainstorm 10 ideas for a name for a package that creates interactive sparklines in tables.</span>'
      )
    ))
  ),
  actionButton("click", "Click me")
)

maybe_fail <- function() {
  if (sample(c(TRUE, FALSE), 1, prob = c(0.25, 0.75))) {
    stop("An error occurred while listing files.")
  }
}

tool_fun <- if (TOOL_OPTS$async) {
  # Use async function for tool call
  if (TOOL_OPTS$with_intent) {
    # Async function with intent
    coro::async(function(path, `_intent` = "") {
      coro::await(coro::async_sleep(runif(1, 1, 10)))
      maybe_fail()
      c("app.R", "data.csv")
    })
  } else {
    # Async function without intent
    coro::async(function(path) {
      coro::await(coro::async_sleep(runif(1, 1, 10)))
      maybe_fail()
      c("app.R", "data.csv")
    })
  }
} else {
  # Synchronous version
  if (TOOL_OPTS$with_intent) {
    # Synchronous function with intent
    function(path, `_intent` = "") {
      Sys.sleep(runif(1, 1, 3))
      maybe_fail()
      c("app.R", "data.csv")
    }
  } else {
    # Synchronous function without intent
    function(path) {
      Sys.sleep(runif(1, 1, 3))
      maybe_fail()
      c("app.R", "data.csv")
    }
  }
}

tool_args <- list(
  path = type_string("Path to the directory to list files"),
  `_intent` = if (TOOL_OPTS$with_intent) {
    type_string(
      "Reason for the request to explain the tool call to the user"
    )
  }
)

tool_annotations <- list(
  title = if (TOOL_OPTS$with_title) "List Files",
  description = "This tool lists files in the specified directory.",
  icon = if (TOOL_OPTS$with_icon) bsicons::bs_icon("folder2-open")
)

server <- function(input, output, session) {
  packaged_list_files_tool <- tool(
    tool_fun,
    "List files in the user's current directory. Always check again when asked.",
    arguments = purrr::compact(tool_args),
    name = "list_file",
    annotations = purrr::compact(tool_annotations)
  )

  client <- chat(PROVIDER_MODEL)
  client$register_tool(packaged_list_files_tool)

  chat_mod_server("chat", client)

  observeEvent(input$click, {
    updateActionButton(
      session,
      "click",
      label = sprintf("Clicked %d times", input$click)
    )
  })
}

shinyApp(ui, server)
