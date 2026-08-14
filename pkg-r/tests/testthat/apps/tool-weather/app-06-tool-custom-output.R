library(shiny)
library(bslib)
library(ellmer)
library(shinychat)
library(weathR)

# This example replaces shinychat's default tool-result card with standalone UI.
# The activity row remains while the tool runs; when the result settles, the
# call leaves the row and the returned value box renders below it.

WeatherToolResult <- S7::new_class(
  "WeatherToolResult",
  parent = ContentToolResult,
  properties = list(
    location_name = S7::class_character
  )
)

contents_shinychat <- S7::new_external_generic(
  "shinychat",
  "contents_shinychat",
  "contents"
)

S7::method(contents_shinychat, WeatherToolResult) <- function(content) {
  current <- content@value[1, ]

  bslib::value_box(
    title = content@location_name,
    value = current$skies,
    showcase = bsicons::bs_icon("cloud-sun"),
    full_screen = TRUE,
    sprintf(
      "%s°F (High: %s°F, Low: %s°F)",
      current$temp,
      max(content@value$temp),
      min(content@value$temp)
    )
  )
}

get_weather_forecast <- tool(
  function(lat, lon, location_name) {
    WeatherToolResult(
      point_tomorrow(lat, lon, short = FALSE),
      location_name = location_name
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
    title = "Getting weather forecast",
    icon = bsicons::bs_icon("cloud-sun")
  )
)

ui <- function(req) {
  page_fillable(
    chat_ui("chat")
  )
}

server <- function(input, output, session) {
  client <- ellmer::chat("openai/gpt-4.1-nano")
  # client <- ellmer::chat_ollama(model = "mistral-nemo")
  client$register_tool(get_weather_forecast)
  chat_server("chat", client)
}

shinyApp(ui, server, enableBookmarking = "url")
