library(shiny)
library(bslib)
library(ellmer)
library(shinychat)
library(weathR)

get_weather_forecast <- tool(
  function(lat, lon, location_name) {
    forecast <- point_tomorrow(lat, lon, short = FALSE)

    icon <- if (any(forecast$temp > 70)) {
      bsicons::bs_icon("sun-fill")
    } else if (any(forecast$temp < 45)) {
      bsicons::bs_icon("snow")
    } else {
      bsicons::bs_icon("cloud-sun-fill")
    }

    ContentToolResult(
      forecast,
      extra = list(
        display = list(
          title = paste("Weather Forecast for", location_name),
          icon = icon
        )
      )
    )
  },
  name = "get_weather_forecast",
  description = "Get the weather forecast for a location.",
  arguments = list(
    lat = type_number("Latitude"),
    lon = type_number("Longitude"),
    location_name = type_string("Name of the location for display to the user")
  ),
  annotations = tool_annotations(
    title = "Weather Forecast",
    icon = bsicons::bs_icon("cloud-sun")
  )
)

ui <- function(req) {
  page_fillable(
    chat_mod_ui("chat")
  )
}

server <- function(input, output, session) {
  client <<- ellmer::chat("openai/gpt-4.1-nano")
  # client <<- ellmer::chat_ollama(model = "mistral-nemo")
  client$register_tool(get_weather_forecast)
  chat_mod_server("chat", client)
}

shinyApp(ui, server, enableBookmarking = "url")
