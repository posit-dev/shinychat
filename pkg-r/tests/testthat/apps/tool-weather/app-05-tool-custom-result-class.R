library(shiny)
library(bslib)
library(ellmer)
library(shinychat)
library(weathR)

# This example shows how to use a custom tool result class. It extends the
# contents_shinychat() generic to compute the HTML table on the fly when we
# render the result in the chat interface. This allows the tool result object to
# be lighter-weight and to only hold the raw data and metadata, without needing
# to also pre-compute the HTML table.

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
  # Call the super method for ContentToolResult to get shinychat's defaults
  res <- contents_shinychat(S7::super(content, ContentToolResult))

  # Then update the result object with more specific content
  res$value <- gt::as_raw_html(gt::gt(content@value))
  res$value_type <- "html"
  res$title <- paste("Weather Forecast for", content@location_name)

  res
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
  client <- ellmer::chat("openai/gpt-4.1-nano")
  # client <- ellmer::chat_ollama(model = "mistral-nemo")
  client$register_tool(get_weather_forecast)
  chat_mod_server("chat", client)
}

shinyApp(ui, server, enableBookmarking = "url")
