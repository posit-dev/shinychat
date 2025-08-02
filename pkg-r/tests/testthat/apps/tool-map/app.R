library(shiny)
library(bslib)
library(ellmer)
library(leaflet)
pkgload::load_all()
library(shinychat)

tool_show_map <- tool(
  function(lat, lon, title, description) {
    popup_content <- sprintf(
      "<strong>%s</strong><br>%s",
      title,
      description
    )

    map <- leaflet() |>
      addTiles() |>
      addMarkers(lat = lat, lng = lon, popup = popup_content) |>
      setView(lng = lon, lat = lat, zoom = 13)

    ContentToolResult(
      value = "Map shown to the user.",
      extra = list(
        display = list(
          html = map,
          show_request = FALSE,
          open = TRUE
        ),
        title = sprintf("Map of %s", title)
      )
    )
  },
  name = "tool_show_map",
  description = r"(Show a map with a marker.

Use this tool whenever you're talking about a location with the user.
)",
  arguments = list(
    lat = type_number("Latitude"),
    lon = type_number("Longitude"),
    title = type_string("Title for the location"),
    description = type_string(
      "A short description of the location, based on the context of the conversation so far or your knowledge of the location."
    )
  ),
  annotations = list(
    title = "Map",
    icon = r"(<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="currentColor" class="bi bi-geo-alt-fill" viewBox="0 0 16 16">
  <path d="M8 16s6-5.686 6-10A6 6 0 0 0 2 6c0 4.314 6 10 6 10m0-7a3 3 0 1 1 0-6 3 3 0 0 1 0 6"/>
</svg>)"
  )
)

ui <- function(req) {
  page_fillable(
    chat_mod_ui("chat"),
    htmltools::findDependencies(
      tool_show_map(34, 45, "", "")@extra$display$html
    )
  )
}

server <- function(input, output, session) {
  client <<- ellmer::chat(
    "openai/gpt-4.1-nano",
    system_prompt = r"(
You're a helpful guide who can tell users about places and show them maps.

Anytime you mention a location, use the `tool_show_map` tool to show a map with a marker at the location. Don't make the user ask to see the map, just show it automatically when it'd be relevant to have a visual.)"
  )
  client$register_tool(tool_show_map)
  chat_mod_server("chat", client)
}

shinyApp(ui, server, enableBookmarking = "disable")
