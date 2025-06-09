library(shiny)
library(coro)
library(bslib)
library(shinychat)

break_string_random <- function(
  input_string,
  avg_size = 10
) {
  if (!is.character(input_string) || length(input_string) != 1) {
    stop("Input must be a single character string")
  }

  total_length <- nchar(input_string)
  if (total_length == 0) {
    return(character(0))
  }

  ends <- sort(sample(
    nchar(input_string),
    size = round(total_length / avg_size),
    replace = FALSE
  ))
  ends <- c(ends, total_length)
  starts <- c(1, ends[-length(ends)] + 1)

  substring(input_string, starts, ends)
}


# Define a generator that yields a random response
# (imagine this is a more sophisticated AI generator)
random_response_generator <- async_generator(function(delay = 0.05) {
  files <- dir(pattern = "response-.*.md$")
  response <- paste(readLines(sample(files, 1)), collapse = "\n")

  await(async_sleep(1))
  for (chunk in break_string_random(response)) {
    yield(chunk)
    await(async_sleep(delay))
  }
})

ui <- page_fillable(
  layout_columns(
    col_widths = c(8, 3, 1),
    fill = FALSE,
    actionButton("generate", "Generate response"),
    div(
      class = "d-flex justify-content-center align-items-center h-100",
      selectInput(
        "speed",
        NULL,
        choices = c("Fast", "Medium", "Slow"),
        selected = "Medium",
        selectize = FALSE
      )
    ),
    div(
      class = "d-flex justify-content-center align-items-center h-100",
      input_dark_mode()
    ),
  ),
  card(
    card_header("Streaming Output"),
    output_markdown_stream(
      "stream",
      `code-theme-light` = "gradient-light",
      `code-theme-dark` = "gradient-dark"
    )
  ),
  useBusyIndicators(spinners = FALSE, pulse = TRUE)
)

server <- function(input, output, session) {
  observeEvent(input$generate, {
    delay <- switch(input$speed, Fast = 0.01, Medium = 0.05, Slow = 0.1)
    markdown_stream("stream", random_response_generator(delay))
  })
}

shinyApp(ui, server)
