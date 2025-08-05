library(shiny)
library(bslib)
library(ellmer)
library(shinychat)
library(weathR)

Sys.setenv("SHINYCHAT_TOOL_DISPLAY" = "rich")

get_weather_forecast <- tool(
  function(lat, lon, location_name) {
    forecast_data <- point_tomorrow(lat, lon, short = FALSE)
    forecast_table <- gt::as_raw_html(gt::gt(forecast_data))

    ContentToolResult(
      forecast_data,
      extra = list(
        display = list(
          html = forecast_table,
          title = paste("Weather Forecast for", location_name)
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
