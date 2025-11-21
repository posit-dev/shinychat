# Format ellmer content for shinychat

Format ellmer content for shinychat

## Usage

``` r
contents_shinychat(content)
```

## Arguments

- content:

  An
  [`ellmer::Content`](https://ellmer.tidyverse.org/reference/Content.html)
  object.

## Value

Returns text, HTML, or web component tags formatted for use in
[`chat_ui()`](https://posit-dev.github.io/shinychat/r/reference/chat_ui.md).

## Extending `contents_shinychat()`

You can extend `contents_shinychat()` to handle custom content types in
your application. `contents_shinychat()` is [an S7
generic](https://rconsortium.github.io/S7/reference/new_generic.html).
If you haven't worked with S7 before, you can learn more about S7
classes, generics and methods in the [S7
documentation](https://rconsortium.github.io/S7/articles/S7.html).

We'll work through a short example creating a custom display for the
results of a tool that gets local weather forecasts. We first need to
create a custom class that extends
[ellmer::ContentToolResult](https://ellmer.tidyverse.org/reference/Content.html).

    library(ellmer)

    WeatherToolResult <- S7::new_class(
      "WeatherToolResult",
      parent = ContentToolResult,
      properties = list(
        location_name = S7::class_character
      )
    )

Next, we'll create a simple
[`ellmer::tool()`](https://ellmer.tidyverse.org/reference/tool.html)
that gets the weather forecast for a location and returns our custom
`WeatherToolResult` class. The custom class works just like a regular
`ContentToolResult`, but it has an additional `location_name` property.

    get_weather_forecast <- tool(
      function(lat, lon, location_name) {
        WeatherToolResult(
          weathR::point_tomorrow(lat, lon, short = FALSE),
          location_name = location_name
        )
      },
      name = "get_weather_forecast",
      description = "Get the weather forecast for a location.",
      arguments = list(
        lat = type_number("Latitude"),
        lon = type_number("Longitude"),
        location_name = type_string("Name of the location for display to the user")
      )
    )

Finally, we can extend `contents_shinychat()` to render our custom
content class for display in the chat interface. The basic process is to
define a `contents_shinychat()` external generic and then implement a
method for your custom class.

    contents_shinychat <- S7::new_external_generic(
      package = "shinychat",
      name = "contents_shinychat",
      dispatch_args = "contents"
    )

    S7::method(contents_shinychat, WeatherToolResult) <- function(content) {
      # Your custom rendering logic here
    }

You can use this pattern to completely customize how the content is
displayed inside shinychat by returning HTML objects directly from this
method.

You can also use this pattern to build upon the default shinychat
display for tool requests and results. By using
[`S7::super()`](https://rconsortium.github.io/S7/reference/super.html),
you can create the object shinychat uses for tool results (or tool
requests), and then modify it to suit your needs.

    S7::method(contents_shinychat, WeatherToolResult) <- function(content) {
      # Call the super method for ContentToolResult to get shinychat's defaults
      res <- contents_shinychat(S7::super(content, ContentToolResult))

      # Then update the result object with more specific content
      # In this case, we render the tool result dataframe as a {gt} table...
      res$value <- gt::as_raw_html(gt::gt(content@value))
      res$value_type <- "html"
      # ...and update the tool result title to include the location name
      res$title <- paste("Weather Forecast for", content@location_name)

      res
    }

Note that you do **not** need to create a new class or extend
`contents_shinychat()` to customize the tool display. Rather, you can
use the strategies discussed in the [Tool Calling UI
article](https://posit-dev.github.io/shinychat/r/articles/tool-ui.html)
to customize the tool request and result display by providing a
`display` list in the `extra` argument of the tool result.
