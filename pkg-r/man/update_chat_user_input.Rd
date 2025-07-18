% Generated by roxygen2: do not edit by hand
% Please edit documentation in R/chat.R
\name{update_chat_user_input}
\alias{update_chat_user_input}
\title{Update the user input of a chat control}
\usage{
update_chat_user_input(
  id,
  ...,
  value = NULL,
  placeholder = NULL,
  submit = FALSE,
  focus = FALSE,
  session = getDefaultReactiveDomain()
)
}
\arguments{
\item{id}{The ID of the chat element}

\item{...}{Currently unused, but reserved for future use.}

\item{value}{The value to set the user input to. If \code{NULL}, the input will not be updated.}

\item{placeholder}{The placeholder text for the user input}

\item{submit}{Whether to automatically submit the text for the user. Requires \code{value}.}

\item{focus}{Whether to move focus to the input element. Requires \code{value}.}

\item{session}{The Shiny session object}
}
\description{
Update the user input of a chat control
}
\examples{
\dontshow{if (interactive()) (if (getRversion() >= "3.4") withAutoprint else force)(\{ # examplesIf}
library(shiny)
library(bslib)
library(shinychat)

ui <- page_fillable(
  chat_ui("chat"),
  layout_columns(
    fill = FALSE,
    actionButton("update_placeholder", "Update placeholder"),
    actionButton("update_value", "Update user input")
  )
)

server <- function(input, output, session) {
  observeEvent(input$update_placeholder, {
    update_chat_user_input("chat", placeholder = "New placeholder text")
  })

  observeEvent(input$update_value, {
    update_chat_user_input("chat", value = "New user input", focus = TRUE)
  })

  observeEvent(input$chat_user_input, {
    response <- paste0("You said: ", input$chat_user_input)
    chat_append("chat", response)
  })
}

shinyApp(ui, server)
\dontshow{\}) # examplesIf}
}
