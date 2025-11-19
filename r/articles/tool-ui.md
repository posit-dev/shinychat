# Tool Calling UI

## Introduction

shinychat automatically displays rich UI for tool calls and results,
providing users with an intuitive view of what tools are being executed
and their outcomes. This tool UI works out-of-the-box with ellmer and
requires no additional configuration to get started.

## Basic tool display

Let’s start with a simple weather forecasting tool to demonstrate the
default behavior:

``` r
library(shinychat)
library(ellmer)
library(weathR) # for forecasts via `point_tomorrow()`

get_weather_forecast <- tool(
  function(lat, lon) {
    point_tomorrow(lat, lon, short = FALSE)
  },
  name = "get_weather_forecast",
  description = "Get the weather forecast for a location.",
  arguments = list(
    lat = type_number("Latitude"),
    lon = type_number("Longitude")
  )
)
```

With [ellmer](https://ellmer.tidyverse.org), you register this tool with
a chat object. When the LLM calls the tool, ellmer automatically
evaluates the tool call and returns the result to the LLM.

``` r
chat <- ellmer::chat("openai/gpt-4.1-nano", echo = "output")
chat$register_tool(get_weather_forecast)
chat$chat("What's the weather in Boston like today?")
```

    ◯ [tool call] get_weather_forecast(lat = 42.3601, lon = -71.0589)
    ● #> [{"time":"2025-08-05 11:00:00 EDT","temp":76,"dewpoint":17.7778,"hum…

    The weather in Boston today is partly sunny with temperatures around 75-76°F
    during the afternoon. There is some humidity at about 64-66%. There is a
    possibility of rain starting around 4 PM, with increasing chances in the
    evening. Winds are coming from the northeast at about 8-10 mph.

If you’re interested in learning more about how to use and create tools
with [ellmer](https://ellmer.tidyverse.org), we recommend reading the
[Tool/function calling
article](https://ellmer.tidyverse.org/articles/tool-calling.html) on the
[ellmer](https://ellmer.tidyverse.org) website.

If you’re working interactively in the R console—and if you’ve set the
`echo = "output"` option—ellmer shows you when tool calls are made and
gives a preview of the tool result.

    ◯ [tool call] get_weather_forecast(lat = 42.3601, lon = -71.0589)
    ● #> [{"time":"2025-08-05 11:00:00 EDT","temp":76,"dewpoint":17.7778,"hum…

shinychat’s tool UI works in the same way, but with rich output displays
that are shown directly in the
[`chat_ui()`](https://posit-dev.github.io/shinychat/r/reference/chat_ui.md)
interface in Shiny apps. When the LLM calls a tool, shinychat
automatically displays the tool request in a collapsed card. Expanding
the card shows the arguments passed to the tool.

When the tool result is completed, shinychat replaces the request with a
card containing the tool result:

If the tool throws an error when called, ellmer captures the error and
shows it to the LLM. shinychat updates the tool card to show the error
message:

When you use
[`chat_app()`](https://posit-dev.github.io/shinychat/r/reference/chat_app.md)
or the chat UI module via
[`chat_mod_ui()`](https://posit-dev.github.io/shinychat/r/reference/chat_app.md)
and
[`chat_mod_server()`](https://posit-dev.github.io/shinychat/r/reference/chat_app.md),
shinychat automatically handles tool requests and results, displaying
them in the chat interface.

On the other hand, if you’re using
[`chat_ui()`](https://posit-dev.github.io/shinychat/r/reference/chat_ui.md)
and calling
[`chat_append()`](https://posit-dev.github.io/shinychat/r/reference/chat_append.md)
to stream the chat output, you’ll need to make sure that ellmer streams
tool requests and results to shinychat by setting `stream = "content"`
in the `$stream_async()` call.

``` r
server <- function(input, output, session) {
  client <- ellmer::chat("openai/gpt-4.1-nano")
  client$register_tool(get_weather_forecast)

  observeEvent(input$chat_user_input, {
    stream <- client$stream_async(input$chat_user_input, stream = "content")
    chat_append("chat", stream)
  })
}
```

Setting `stream = "content"` tells ellmer to stream
[`ellmer::Content`](https://ellmer.tidyverse.org/reference/Content.html)
objects rather than plain text. As a result,
[`ellmer::ContentToolRequest`](https://ellmer.tidyverse.org/reference/Content.html)
and
[`ellmer::ContentToolResult`](https://ellmer.tidyverse.org/reference/Content.html)
objects are streamed to shinychat, which automatically displays the tool
requests and results in the chat interface.

## Tool title and icon

### Via tool annotations

You can improve the visual presentation by adding `annotations` to your
[`ellmer::tool()`](https://ellmer.tidyverse.org/reference/tool.html)
definition using
[`ellmer::tool_annotations()`](https://ellmer.tidyverse.org/reference/tool_annotations.html).
If the tool annotations include a `title` or `icon`, shinychat will use
them in the tool request and result displays.

``` r
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
    icon = bsicons::bs_icon("cloud-sun")
  )
)
```

Now the tool request shows the custom title

and the tool results show both the custom title and the icon.

### Via the tool result

Using tool annotations is an easy way to set the title and icon for all
tool requests and results, but sometimes you’ll want to customize the
display for specific tool calls or results. In these cases, you’ll need
to update your tool function to return an
[`ellmer::ContentToolResult`](https://ellmer.tidyverse.org/reference/Content.html)
object, which takes an `extra` property that includes a list of extra
data to attach to the result.

shinychat looks for and uses a `display` list within `extra` to
customize how the tool result is shown. These properties can be computed
dynamically based on the tool’s input or the data it prepares to show to
the LLM. If this list contains `title` and `icon` items, these values
override the values in the tool’s annotations.

One useful strategy is to include display parameters in the tool’s
function signature, allowing the LLM to include context or additional
information in the tool call. In the example below, we’ll let the LLM
write the tool result title and we’ll pick an icon based on the
forecasted temperatures. Note that we need to also update the tool’s
`arguments` to include the new `location_name` parameter so that the LLM
can provide a meaningful title.

``` r
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
```

Now when the tool result is completed, shinychat shows the custom title
and icon based on the forecasted temperature:

## Tool intent

In the last example, we saw that we could include arguments in the tool
function to let the LLM write some of the display text for us (e.g., the
location name).

This strategy is so useful that shinychat automatically supports it for
an `` `_intent` `` argument. When `` `_intent` `` is present in the
tool’s arguments, shinychat shows this value in the tool request and
result titles as the *reason the tool was called*.

To demonstrate, we’ll use take a break from our weather tool and create
a tool that simply generates a random number. On its own, the tool
doesn’t need any arguments, but we include a `` `_intent` `` argument in
the tool function and we include a description to explain its purpose.

``` r
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
    title = "Random Number Generator",
    icon = bsicons::bs_icon("dice-3-fill")
  )
)
```

When the tool is called, shinychat shows the reason the LLM called the
tool in the header of the tool card.

## Customizing tool result display

We’ve already seen that we can [customize the tool title and
icon](#via-the-tool-result) by returning a `ContentToolResult` object
from our tool function and specifying `title` and `icon` in the
`extra$display` list.

shinychat uses the `display` list for two additional categories of
customization:

1.  Alternative `html`, `markdown`, or `text` to show the user in place
    of the text value shown to the LLM.
2.  Options to control how the tool result is presented.

### Alternative display content

By default, shinychat shows the tool result’s `value` property as a code
block to the user. This is often sufficient, but in some cases your tool
may collect or prepare data that could be better presented to users in a
different format.

For example, our weather tool returns a data frame with the forecast for
the next day. The LLM sees a JSON representation of this data frame, but
users would likely prefer to see a nicely formatted table.

shinychat looks for the following properties in the `display` list and
shows the user the first available display in the following order:

1.  `html`: An HTML string or object. This can be HTML generated via R
    packages like [htmltools](https://github.com/rstudio/htmltools),
    [gt](https://gt.rstudio.com),
    [reactable](https://glin.github.io/reactable/) or even
    [htmlwidgets](https://github.com/ramnathv/htmlwidgets).
2.  `markdown`: A markdown string that is automatically rendered as rich
    HTML in shinychat.
3.  `text`: A plain text string that is shown without code formatting.

Keep in mind that the content you show to your users should faithfully
represent the `value` shown to the LLM. Our weather tool is a great
example—a JSON object isn’t very user-friendly, but a table showing the
forecast data is perfect.

#### Alternative HTML display

In the following example, we’ll update the `get_weather_forecast()` to
show the user a nicely formatted HTML table using
[gt](https://gt.rstudio.com).

``` r
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
```

Expand the tool result card to see the forecast as a table.

#### Alternative markdown display

You can also prepare markdown content to show your users based on the
tool result. It’s less appropriate in our weather tool, but we could use
markdown to summarize the forecast in a few sentences.

``` r
get_weather_forecast <- tool(
  function(lat, lon, location_name) {
    forecast_data <- point_tomorrow(lat, lon, short = FALSE)

    temp_current <- forecast_data$temp[1]
    skies_current <- forecast_data$skies[[1]]

    temp_high <- max(forecast_data$temp)
    temp_low <- min(forecast_data$temp)

    humidity <- round(mean(forecast_data$humidity), 1)
    skies <- table(forecast_data$skies)
    skies <- names(skies)[which.max(skies)]

    forecast_summary <- glue::glue(
      "In **{location_name}**, it's currently {temp_current}°F with _{tolower(skies_current)}_ skies. ",
      "Today's high will be {temp_high}°F and the low will be {temp_low}°F. ",
      "Humidity is around {humidity}%. ",
      "Look for **{tolower(skies)}** skies throughout the day."
    )

    ContentToolResult(
      forecast_data,
      extra = list(
        display = list(
          markdown = forecast_summary,
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
```

### Display Options

In addition to customizing the [tool title and
icon](#via-the-tool-result) and providing alternative display content,
you can also control how the tool result is presented using options in
the `display` list.

shinychat supports several options in the `display` list to control how
results are presented:

- **`show_request = FALSE`**: Hide the tool call details from the tool
  results display.

  This is useful when you have rich output and the tool call details are
  clear from the rest of the display. For example, it might be
  appropriate to hide the request details when showing a [full formatted
  table of results](#alternative-html-display).

- **`open = TRUE`**: Expand the result panel by default.

  This is most useful when you’ve [customized the tool
  display](#alternative-display-content) to include an `{htmlwidget}` or
  other rich content that users should see immediately.

- **`title`** and **`icon`**: Choose the title and icon displayed in the
  tool result card header.

## Global display options

shinychat uses the rich tool UI described above by default, but you can
choose to hide all tool calls or use shinychat’s basic display without
allowing for rich or alternative content displays.

Most users won’t need to customize these options, but it can be useful
to use the basic display for debugging or verification purposes when you
need to see the tool arguments and outputs exactly as written and seen
by the LLM.

To adjust the display for debugging or verification purposes, set the
`shinychat.tool_display` option (or the `SHINYCHAT_TOOL_DISPLAY`
environment variable) to one of the following values:

``` r
# Disable tool UI entirely
options(shinychat.tool_display = "none")

# Use basic text-based display (useful for verifying inputs/outputs)
options(shinychat.tool_display = "basic")

# Default rich display applies customizations from tool authors
options(shinychat.tool_display = "rich")
```

For most users, the default `"rich"` display provides the best
experience.
