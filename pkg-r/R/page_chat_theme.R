#' Create a theme for `page_chat()`
#'
#' `page_chat_theme()` layers page-scoped surface, chat-radius, and density
#' tokens and system typography over bslib's `"shiny"` preset. Supply a
#' different `preset` to start from another bslib or Bootswatch preset, or pass
#' a regular [bslib::bs_theme()] directly to [page_chat()] to omit the page-chat
#' baseline.
#'
#' @param ... Sass variables forwarded to [bslib::bs_theme()]. Values supplied
#'   here override the page-chat defaults.
#' @param preset A bslib or Bootswatch preset name.
#'
#' @returns A [bslib::bs_theme()] suitable for the `theme` argument of
#'   [page_chat()].
#' @export
page_chat_theme <- function(..., preset = "shiny") {
  defaults <- list(
    "font-family-sans-serif" = paste(
      'ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI",',
      "sans-serif"
    ),
    "font-family-base" = "$font-family-sans-serif",
    "font-family-monospace" = paste(
      'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono",',
      '"Courier New", monospace'
    ),
    "web-font-path" = FALSE,
    "shiny-chat-page-header-height" = "3.25rem",
    "shiny-chat-page-header-padding-y" = "0.25rem",
    "shiny-chat-page-sidebar-padding" = "0.875rem",
    "shiny-chat-page-title-gap" = "0.375rem",
    "shiny-chat-page-title-font-size" = "0.9375rem",
    "shiny-chat-page-title-font-weight" = 600,
    "shiny-chat-page-controls-gap" = "0.375rem",
    "shiny-chat-page-nav-link-gap" = "0.3125rem",
    "shiny-chat-page-nav-link-padding-y" = "0.375rem",
    "shiny-chat-page-nav-link-padding-x" = "0.625rem",
    "shiny-chat-page-nav-link-font-size" = "0.875rem",
    "shiny-chat-page-nav-link-font-weight" = 500,
    "shiny-chat-page-panel-padding-block" = "1.25rem",
    "shiny-chat-page-panel-padding-block-mobile" = "1rem",
    "shiny-chat-page-panel-padding-inline" = "1rem",
    "shiny-chat-page-surface-bg" = "var(--bs-body-bg)",
    "shiny-chat-page-sidebar-bg" = "var(--bs-secondary-bg)",
    "shiny-chat-page-canvas-bg" = "var(--bs-tertiary-bg)",
    "shiny-chat-suggestion-card-border-radius" = "var(--bs-border-radius)",
    "shiny-chat-user-message-border-radius" = "var(--bs-border-radius)",
    "shiny-chat-user-message-padding" = "0.5rem 0.75rem",
    "shiny-chat-user-assistant-gap-reduction" = "0.5rem"
  )
  variables <- rlang::dots_list(!!!defaults, ..., .homonyms = "last")

  theme <- rlang::exec(bslib::bs_theme, preset = preset, !!!variables)
  bslib::bs_add_rules(
    theme,
    "
    :root {
      --shiny-chat-page-header-height: #{$shiny-chat-page-header-height};
      --shiny-chat-page-header-padding-y: #{$shiny-chat-page-header-padding-y};
      --shiny-chat-page-sidebar-padding: #{$shiny-chat-page-sidebar-padding};
      --shiny-chat-page-title-gap: #{$shiny-chat-page-title-gap};
      --shiny-chat-page-title-font-size: #{$shiny-chat-page-title-font-size};
      --shiny-chat-page-title-font-weight: #{$shiny-chat-page-title-font-weight};
      --shiny-chat-page-controls-gap: #{$shiny-chat-page-controls-gap};
      --shiny-chat-page-nav-link-gap: #{$shiny-chat-page-nav-link-gap};
      --shiny-chat-page-nav-link-padding-y: #{$shiny-chat-page-nav-link-padding-y};
      --shiny-chat-page-nav-link-padding-x: #{$shiny-chat-page-nav-link-padding-x};
      --shiny-chat-page-nav-link-font-size: #{$shiny-chat-page-nav-link-font-size};
      --shiny-chat-page-nav-link-font-weight: #{$shiny-chat-page-nav-link-font-weight};
      --shiny-chat-page-panel-padding-block: #{$shiny-chat-page-panel-padding-block};
      --shiny-chat-page-panel-padding-block-mobile: #{$shiny-chat-page-panel-padding-block-mobile};
      --shiny-chat-page-panel-padding-inline: #{$shiny-chat-page-panel-padding-inline};
      --shiny-chat-page-surface-bg: #{$shiny-chat-page-surface-bg};
      --shiny-chat-page-sidebar-bg: #{$shiny-chat-page-sidebar-bg};
      --shiny-chat-page-canvas-bg: #{$shiny-chat-page-canvas-bg};
      --shiny-chat-suggestion-card-border-radius: #{$shiny-chat-suggestion-card-border-radius};
      --shiny-chat-user-message-border-radius: #{$shiny-chat-user-message-border-radius};
      --shiny-chat-user-message-padding: #{$shiny-chat-user-message-padding};
      --shiny-chat-user-assistant-gap-reduction: #{$shiny-chat-user-assistant-gap-reduction};
    }
    "
  )
}
