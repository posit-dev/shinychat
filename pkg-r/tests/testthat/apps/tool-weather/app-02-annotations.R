library(shiny)
library(bslib)
library(ellmer)
library(shinychat)
library(weathR)

get_weather_forecast <- tool(
  function(lat, lon) {
    point_tomorrow(lat, lon, short = FALSE)
  },
  name = "get_weather_forecast",
  description = "Get the weather forecast for a location.",
  arguments = list(
    lat = type_number("Latitude"),
    lon = type_number("Longitude")
  ),
  annotations = tool_annotations(
    title = "Weather Forecast",
    icon = bsicons::bs_icon("globe-americas")
  )
)

ui <- function(req) {
  page_fillable(
    chat_mod_ui("chat")
  )
}

server <- function(input, output, session) {
  client <- ellmer::chat("openai/gpt-4.1-nano")
  # client <- ellmer::chat_ollama(model = "mistral:v0.3")
  client$register_tool(get_weather_forecast)
  chat_mod_server("chat", client)
}

shinyApp(ui, server, enableBookmarking = "url")
