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
    "shiny-chat-page-fill-padding" = paste0(
      'unquote("max(1rem, env(safe-area-inset-left), ',
      'env(safe-area-inset-right))")'
    ),
    "shiny-chat-page-input-padding-bottom" = paste0(
      'unquote("max(1rem, env(safe-area-inset-bottom))")'
    ),
    "shiny-chat-page-surface-bg" = "var(--bs-body-bg)",
    "shiny-chat-page-sidebar-bg" = "var(--bs-secondary-bg)",
    "shiny-chat-page-canvas-bg" = "var(--bs-tertiary-bg)",
    "shiny-chat-page-artifact-bg" = "var(--shiny-chat-page-surface-bg)",
    "shiny-chat-page-artifact-box-shadow" = "none",
    "shiny-chat-page-artifact-header-bg" = "var(--shiny-chat-page-canvas-bg)",
    "shiny-chat-suggestion-card-border-radius" = "var(--bs-border-radius)",
    "shiny-chat-user-message-border-radius" = "var(--bs-border-radius)",
    "shiny-chat-user-message-padding" = "0.5rem 0.75rem",
    "shiny-chat-user-assistant-gap-reduction" = "0.5rem"
  )
  variables <- rlang::dots_list(!!!defaults, ..., .homonyms = "last")

  theme <- rlang::exec(bslib::bs_theme, preset = preset, !!!variables)
  # Keep these rules in sync with pkg-py/src/shinychat/_page_chat_theme.py.
  # The packages inject runtime Sass through different framework APIs, so the
  # duplication is intentional.
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
      --shiny-chat-page-fill-padding: #{$shiny-chat-page-fill-padding};
      --shiny-chat-page-input-padding-bottom: #{$shiny-chat-page-input-padding-bottom};
      --shiny-chat-page-surface-bg: #{$shiny-chat-page-surface-bg};
      --shiny-chat-page-sidebar-bg: #{$shiny-chat-page-sidebar-bg};
      --shiny-chat-page-canvas-bg: #{$shiny-chat-page-canvas-bg};
      --shiny-chat-page-artifact-bg: #{$shiny-chat-page-artifact-bg};
      --shiny-chat-page-artifact-box-shadow: #{$shiny-chat-page-artifact-box-shadow};
      --shiny-chat-page-artifact-header-bg: #{$shiny-chat-page-artifact-header-bg};
      --shiny-chat-suggestion-card-border-radius: #{$shiny-chat-suggestion-card-border-radius};
      --shiny-chat-user-message-border-radius: #{$shiny-chat-user-message-border-radius};
      --shiny-chat-user-message-padding: #{$shiny-chat-user-message-padding};
      --shiny-chat-user-assistant-gap-reduction: #{$shiny-chat-user-assistant-gap-reduction};
    }

    shiny-chat-page :is(
      .shiny-chat-page-header,
      .shiny-chat-page-sidebar,
      .shiny-chat-page-panel
    ) :is(.form-control, .form-select) {
      border-color: var(--bs-border-color, currentcolor);
      border-radius: var(--bs-border-radius-sm, 0.25rem);
    }

    shiny-chat-page :is(
      .shiny-chat-page-header,
      .shiny-chat-page-sidebar,
      .shiny-chat-page-panel
    ) :is(.form-control, .form-select):focus {
      border-color: var(--bs-primary, #0d6efd);
      box-shadow: 0 0 0 0.2rem color-mix(
        in srgb,
        var(--bs-primary, #0d6efd) 32%,
        transparent
      );
    }

    .shiny-chat-page-home > shiny-chat-container {
      --shiny-chat-fill-padding: var(--shiny-chat-page-fill-padding);
      --shiny-chat-input-padding-bottom: var(--shiny-chat-page-input-padding-bottom);
    }

    .shiny-chat-page-home .shiny-chat-artifact {
      background: var(--shiny-chat-page-artifact-bg);
      box-shadow: var(--shiny-chat-page-artifact-box-shadow);
    }

    .shiny-chat-page-home .shiny-chat-artifact-header {
      background: var(--shiny-chat-page-artifact-header-bg);
    }
    "
  )
}
