from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from shiny.ui import Theme

_PAGE_CHAT_THEME_DEFAULTS = {
    "font-family-sans-serif": (
        'ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", '
        "sans-serif"
    ),
    "font-family-base": "$font-family-sans-serif",
    "font-family-monospace": (
        'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", '
        '"Courier New", monospace'
    ),
    "web-font-path": False,
    "shiny-chat-page-header-height": "3.25rem",
    "shiny-chat-page-header-padding-y": "0.25rem",
    "shiny-chat-page-sidebar-padding": "0.875rem",
    "shiny-chat-page-title-gap": "0.375rem",
    "shiny-chat-page-title-font-size": "0.9375rem",
    "shiny-chat-page-title-font-weight": 600,
    "shiny-chat-page-controls-gap": "0.375rem",
    "shiny-chat-page-nav-link-gap": "0.3125rem",
    "shiny-chat-page-nav-link-padding-y": "0.375rem",
    "shiny-chat-page-nav-link-padding-x": "0.625rem",
    "shiny-chat-page-nav-link-font-size": "0.875rem",
    "shiny-chat-page-nav-link-font-weight": 500,
    "shiny-chat-page-panel-padding-block": "1.25rem",
    "shiny-chat-page-panel-padding-block-mobile": "1rem",
    "shiny-chat-page-panel-padding-inline": "1rem",
    "shiny-chat-page-fill-padding": (
        'unquote("max(1rem, env(safe-area-inset-left), '
        'env(safe-area-inset-right))")'
    ),
    "shiny-chat-page-input-padding-bottom": (
        'unquote("max(1rem, env(safe-area-inset-bottom))")'
    ),
    "shiny-chat-page-surface-bg": "var(--bs-body-bg)",
    "shiny-chat-page-sidebar-bg": "var(--bs-secondary-bg)",
    "shiny-chat-page-canvas-bg": "var(--bs-tertiary-bg)",
    "shiny-chat-page-artifact-bg": "var(--shiny-chat-page-surface-bg)",
    "shiny-chat-page-artifact-box-shadow": "none",
    "shiny-chat-page-artifact-header-bg": "var(--shiny-chat-page-canvas-bg)",
    "shiny-chat-suggestion-card-border-radius": "var(--bs-border-radius)",
    "shiny-chat-user-message-border-radius": "var(--bs-border-radius)",
    "shiny-chat-user-message-padding": "0.5rem 0.75rem",
    "shiny-chat-user-assistant-gap-reduction": "0.5rem",
}

# Keep this Sass in sync with the equivalent rules in pkg-r/R/page_chat_theme.R.
# Python and R inject runtime Sass through different framework APIs, so sharing
# a source file would add package-path and runtime dependency complexity.
_PAGE_CHAT_THEME_RULES = """
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
"""


def page_chat_theme(
    preset: str | None = "shiny",
    **variables: str | float | int | bool | None,
) -> "Theme":
    """
    Create a theme for :func:`~shinychat.page_chat`.

    The default layers page-scoped surface, chat-radius, and density tokens and
    system typography over Shiny's ``"shiny"`` preset. Pass another ``preset``
    or Sass-variable overrides to apply application branding while retaining
    the page-chat layout treatment. Pass a :class:`shiny.ui.Theme` directly to
    :func:`~shinychat.page_chat` to use a completely custom theme.

    Parameters
    ----------
    preset
        A Shiny or Bootswatch preset name.
    **variables
        Sass-variable overrides. Keys may use either ``snake_case`` or
        ``kebab-case`` names.

    Returns
    -------
    :
        A :class:`shiny.ui.Theme` suitable for ``page_chat(theme=)``.
    """
    from shiny import ui

    theme = ui.Theme(preset=preset, name="shinychat-page")
    theme.add_defaults(**_PAGE_CHAT_THEME_DEFAULTS)
    theme.add_defaults(**variables)
    theme.add_rules(_PAGE_CHAT_THEME_RULES)
    return theme
