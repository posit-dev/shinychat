library(shiny)
library(bslib)
library(shinychat)
library(ellmer)
library(bsicons)
library(weathR)
library(gt)
library(glue)
library(rlang)

# Cache weather.gov responses: one fetch reused across all screenshot states.
.weather_cache <- new.env(parent = emptyenv())
point_tomorrow <- function(lat, lon, short = FALSE) {
  key <- paste(lat, lon, short)
  if (is.null(.weather_cache[[key]])) {
    .weather_cache[[key]] <- weathR::point_tomorrow(lat, lon, short = short)
  }
  .weather_cache[[key]]
}

weather_args <- list(
  lat = type_number("Latitude"),
  lon = type_number("Longitude")
)

tool_basic <- tool(
  function(lat, lon) {
    point_tomorrow(lat, lon, short = FALSE)
  },
  name = "get_weather_forecast",
  description = "Get the weather forecast for a location.",
  arguments = weather_args
)

tool_annotated <- tool(
  function(lat, lon) {
    point_tomorrow(lat, lon, short = FALSE)
  },
  name = "get_weather_forecast",
  description = "Get the weather forecast for a location.",
  arguments = weather_args,
  annotations = tool_annotations(
    title = "Getting weather forecast",
    icon = bs_icon("cloud-sun")
  )
)

weather_args_location <- c(
  weather_args,
  list(
    location_name = type_string("Name of the location for display to the user")
  )
)

tool_result_fields <- tool(
  function(lat, lon, location_name) {
    forecast <- point_tomorrow(lat, lon, short = FALSE)

    icon <- if (any(forecast$temp > 70)) {
      bs_icon("sun-fill")
    } else if (any(forecast$temp < 45)) {
      bs_icon("snow")
    } else {
      bs_icon("cloud-sun-fill")
    }

    ContentToolResult(
      forecast,
      extra = list(
        display = tool_result_display(
          title = paste("Got weather forecast for", location_name),
          icon = icon,
          label = location_name,
          value_preview = paste(nrow(forecast), "hourly readings")
        )
      )
    )
  },
  name = "get_weather_forecast",
  description = "Get the weather forecast for a location.",
  arguments = weather_args_location,
  annotations = tool_annotations(
    title = "Getting weather forecast",
    icon = bs_icon("cloud-sun")
  )
)

tool_html <- tool(
  function(lat, lon, location_name) {
    forecast_data <- point_tomorrow(lat, lon, short = FALSE)
    forecast_table <- gt::as_raw_html(gt::gt(forecast_data))

    ContentToolResult(
      forecast_data,
      extra = list(
        display = tool_result_display(
          html = forecast_table,
          title = paste("Got weather forecast for", location_name),
          label = location_name,
          value_preview = paste(nrow(forecast_data), "hourly readings"),
          show_request = FALSE,
          open = TRUE,
          full_screen = TRUE,
          footer = htmltools::tags$small("Forecast data from weather.gov"),
          open_style = "framed"
        )
      )
    )
  },
  name = "get_weather_forecast",
  description = "Get the weather forecast for a location.",
  arguments = weather_args_location,
  annotations = tool_annotations(
    title = "Getting weather forecast",
    icon = bs_icon("cloud-sun")
  )
)

tool_markdown <- tool(
  function(lat, lon, location_name) {
    forecast_data <- point_tomorrow(lat, lon, short = FALSE)

    temp_current <- forecast_data$temp[1]
    skies_current <- forecast_data$skies[[1]]

    temp_high <- max(forecast_data$temp)
    temp_low <- min(forecast_data$temp)

    humidity <- round(mean(forecast_data$humidity), 1)
    skies <- table(forecast_data$skies)
    skies <- names(skies)[which.max(skies)]

    forecast_summary <- glue(
      "In **{location_name}**, it's currently {temp_current}°F with _{tolower(skies_current)}_ skies. ",
      "Today's high will be {temp_high}°F and the low will be {temp_low}°F. ",
      "Humidity is around {humidity}%. ",
      "Look for **{tolower(skies)}** skies throughout the day."
    )

    ContentToolResult(
      forecast_data,
      extra = list(
        display = tool_result_display(
          markdown = forecast_summary,
          title = paste("Got weather forecast for", location_name)
        )
      )
    )
  },
  name = "get_weather_forecast",
  description = "Get the weather forecast for a location.",
  arguments = weather_args_location,
  annotations = tool_annotations(
    title = "Getting weather forecast",
    icon = bs_icon("cloud-sun")
  )
)

tool_random_number <- tool(
  function(`_intent`) {
    runif(1)
  },
  name = "tool_random_number",
  description = "Generate a random number.",
  arguments = list(
    `_intent` = type_string(
      "A short snippet used for display purposes to explain the call to the user."
    )
  ),
  annotations = tool_annotations(
    title = "Generating random number",
    icon = bs_icon("dice-3-fill")
  )
)

weather_request <- function(tool, id, arguments) {
  ContentToolRequest(
    id = id,
    name = "get_weather_forecast",
    arguments = arguments,
    tool = tool
  )
}

weather_result <- function(tool, request) {
  value <- do.call(tool, request@arguments)
  if (inherits(value, "ellmer::ContentToolResult")) {
    value@request <- request
    value
  } else {
    ContentToolResult(value, request = request)
  }
}

weather_prompt <- "What's the weather in Boston like today?"
boston <- list(lat = 42.3601, lon = -71.0589)

build_state <- function(state) {
  switch(
    state,
    "basic-running" = list(
      prompt = weather_prompt,
      contents = list(weather_request(tool_basic, "tool_call_001", boston))
    ),
    "basic-settled" = local({
      request <- weather_request(tool_basic, "tool_call_002", boston)
      list(
        prompt = weather_prompt,
        contents = list(request, weather_result(tool_basic, request))
      )
    }),
    "basic-error" = local({
      request <- weather_request(tool_basic, "tool_call_003", boston)
      error_result <- ContentToolResult(
        error = rlang::catch_cnd(
          stop("Failed to retrieve forecast: station not found")
        ),
        request = request
      )
      list(
        prompt = weather_prompt,
        contents = list(request, error_result)
      )
    }),
    "annotations-running" = list(
      prompt = weather_prompt,
      contents = list(weather_request(tool_annotated, "tool_call_004", boston))
    ),
    "annotations-settled" = local({
      request <- weather_request(tool_annotated, "tool_call_005", boston)
      list(
        prompt = weather_prompt,
        contents = list(request, weather_result(tool_annotated, request))
      )
    }),
    "result-fields" = local({
      request <- weather_request(
        tool_result_fields,
        "tool_call_006",
        c(boston, list(location_name = "Boston, MA"))
      )
      list(
        prompt = weather_prompt,
        contents = list(request, weather_result(tool_result_fields, request))
      )
    }),
    "intent" = local({
      request <- ContentToolRequest(
        id = "tool_call_007",
        name = "tool_random_number",
        arguments = list(`_intent` = "Generate a random number for testing"),
        tool = tool_random_number
      )
      result <- ContentToolResult(runif(1), request = request)
      list(
        prompt = "Generate a random number for testing",
        contents = list(request, result)
      )
    }),
    "rich-html" = local({
      request <- weather_request(
        tool_html,
        "tool_call_008",
        c(boston, list(location_name = "Boston, MA"))
      )
      list(
        prompt = weather_prompt,
        contents = list(request, weather_result(tool_html, request))
      )
    }),
    "rich-markdown" = local({
      request <- weather_request(
        tool_markdown,
        "tool_call_009",
        c(boston, list(location_name = "Boston, MA"))
      )
      list(
        prompt = weather_prompt,
        contents = list(request, weather_result(tool_markdown, request))
      )
    }),
    rlang::abort("Unknown state: {state}")
  )
}

ui <- function(req) {
  page_fillable(
    chat_ui("chat")
  )
}

server <- function(input, output, session) {
  observe({
    state <- parseQueryString(session$clientData$url_search)$state %||%
      "basic-running"
    scene <- build_state(state)

    chat_append("chat", scene$prompt, role = "user")
    for (content in scene$contents) {
      chat_append("chat", content)
    }
  })
}

shinyApp(ui, server)
