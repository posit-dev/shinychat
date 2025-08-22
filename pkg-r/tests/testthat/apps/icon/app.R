library(shiny)
library(bslib)
pkgload::load_all()
library(shinychat)
library(bsicons)

ui <- page_fillable(
  title = "Chat Icons",

  layout_columns(
    # Default Bot ----
    div(
      h2("Default Bot"),
      chat_ui(
        id = "chat_default",
        messages = list(
          list(
            content = "Hello! I'm Default Bot. How can I help you today?",
            role = "assistant"
          )
        ),
        icon_assistant = NULL # Uses default robot icon
      )
    ),

    # Animal Bot ----
    div(
      h2("Animal Bot"),
      chat_ui(
        id = "chat_animal",
        messages = list("Hello! I'm Animal Bot. How can I help you today?"),
        icon_assistant = fontawesome::fa("otter", )
      ),
      selectInput(
        "animal",
        "Animal",
        choices = c("Otter", "Hippo", "Frog", "Dove"),
        selected = "Otter"
      )
    ),

    # SVG Bot ----
    div(
      h2("SVG Bot"),
      chat_ui(
        id = "chat_svg",
        messages = list("Hello! I'm SVG Bot. How can I help you today?"),
        icon_assistant = HTML(
          '
          <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="currentColor" class="bi bi-info-circle-fill icon-svg" viewBox="0 0 16 16">
            <path d="M8 16A8 8 0 1 0 8 0a8 8 0 0 0 0 16m.93-9.412-1 4.705c-.07.34.029.533.304.533.194 0 .487-.07.686-.246l-.088.416c-.287.346-.92.598-1.465.598-.703 0-1.002-.422-.808-1.319l.738-3.468c.064-.293.006-.399-.287-.47l-.451-.081.082-.381 2.29-.287zM8 5.5a1 1 0 1 1 0-2 1 1 0 0 1 0 2"/>
          </svg>
        '
        )
      )
    ),

    # Image Bot ----
    div(
      h2("Image Bot"),
      chat_ui(
        id = "chat_image",
        messages = list("Hello! I'm Image Bot. How can I help you today?"),
        icon_assistant = img(
          src = "img/grace-hopper.jpg",
          class = "icon-image grace-hopper"
        )
      ),
      selectInput(
        "image",
        "Image",
        choices = c("Grace Hopper", "Shiny"),
        selected = "Grace Hopper"
      )
    )
  )
)

server <- function(input, output, session) {
  # Add resource path for images
  addResourcePath("img", "img")

  # Default Bot ----
  observeEvent(input$chat_default_user_input, {
    req(input$chat_default_user_input)

    # Simulate delay
    Sys.sleep(1)

    chat_append(
      "chat_default",
      paste0("You said: ", input$chat_default_user_input)
    )
  })

  # Animal Bot ----
  observeEvent(input$chat_animal_user_input, {
    req(input$chat_animal_user_input)

    # Simulate delay
    Sys.sleep(1)

    animal <- tolower(input$animal)

    # Create icon based on selection
    if (animal == "otter") {
      # Use default icon (NULL)
      icon <- NULL
    } else {
      icon_map <- list(
        "hippo" = "hippo",
        "frog" = "frog",
        "dove" = "dove"
      )

      if (animal %in% names(icon_map)) {
        icon <- fontawesome::fa(
          icon_map[[animal]],
          # fontawesome doesn't support `class` argument, so we use `title`
          title = paste0("icon-", animal)
        )
      } else {
        icon <- NULL
      }
    }

    chat_append(
      "chat_animal",
      paste0(animal, " said: ", input$chat_animal_user_input),
      icon = icon
    )
  })

  # SVG Bot ----
  observeEvent(input$chat_svg_user_input, {
    req(input$chat_svg_user_input)

    chat_append(
      "chat_svg",
      paste0("You said: ", input$chat_svg_user_input)
    )
  })

  # Image Bot ----
  observeEvent(input$chat_image_user_input, {
    req(input$chat_image_user_input)

    # Create icon based on selection
    icon <- NULL
    if (input$image == "Shiny") {
      icon <- img(
        src = "img/shiny.png",
        class = "icon-image shiny"
      )
    }

    chat_append(
      "chat_image",
      paste0("You said: ", input$chat_image_user_input),
      icon = icon
    )
  })
}

shinyApp(ui, server)
