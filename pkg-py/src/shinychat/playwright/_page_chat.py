from __future__ import annotations

from typing import Pattern, Union

from playwright.sync_api import Locator, Page
from playwright.sync_api import expect as playwright_expect

from ._chat import UiBase

PatternStr = Pattern[str]
PatternOrStr = Union[str, PatternStr]
Timeout = Union[float, None]

_DEFAULT_TIMEOUT = 30_000


class PageChatController(UiBase):
    """Controller for :func:`shinychat.page_chat` shell elements.

    Wraps the ``<shiny-chat-page>`` custom element and exposes typed
    sub-locators and helper methods for the most common page-chat test
    operations: navigation, sidebar/mobile-menu state, and header/toolbar
    queries.  Test code that needs an uncommon selector can still reach
    the root locator via ``.loc``.
    """

    loc: Locator
    """Playwright ``Locator`` for the ``<shiny-chat-page>`` element."""

    loc_header: Locator
    """Playwright ``Locator`` for the page header (``.shiny-chat-page-header``)."""

    loc_sidebar: Locator
    """Playwright ``Locator`` for the sidebar (``.shiny-chat-page-sidebar``)."""

    loc_sidebar_toggle: Locator
    """Playwright ``Locator`` for the sidebar/app-menu toggle button."""

    loc_nav: Locator
    """Playwright ``Locator`` for the navigation container (``.shiny-chat-page-nav``)."""

    loc_main: Locator
    """Playwright ``Locator`` for the main content area (``.shiny-chat-page-main``)."""

    loc_body: Locator
    """Playwright ``Locator`` for the body grid area (``.shiny-chat-page-body``)."""

    loc_identity: Locator
    """Playwright ``Locator`` for the identity/title group."""

    loc_identity_title: Locator
    """Playwright ``Locator`` for the identity title text."""

    loc_toolbar: Locator
    """Playwright ``Locator`` for the toolbar (``.shiny-chat-page-toolbar``)."""

    loc_controls: Locator
    """Playwright ``Locator`` for the controls container (``.shiny-chat-page-controls``)."""

    loc_controls_mount_desktop: Locator
    """Playwright ``Locator`` for the desktop controls mount."""

    loc_controls_mount_mobile: Locator
    """Playwright ``Locator`` for the mobile controls mount."""

    def __init__(self, page: Page, id: str) -> None:
        """
        Initializes a new instance of the ``PageChatController`` class.

        Parameters
        ----------
        page
            Playwright ``Page`` of the Shiny app.
        id
            The chat ID used by ``page_chat(id=...)``.  The controller locates
            the ``<shiny-chat-page data-chat-id="{id}">`` element.
        """
        super().__init__(
            page,
            id=id,
            loc=f'shiny-chat-page[data-chat-id="{id}"]',
        )
        self.loc_header = self.loc.locator(".shiny-chat-page-header")
        self.loc_sidebar = self.loc.locator(".shiny-chat-page-sidebar")
        self.loc_sidebar_toggle = self.loc.locator(
            ".shiny-chat-page-sidebar-toggle"
        )
        self.loc_nav = self.loc.locator(".shiny-chat-page-nav")
        self.loc_main = self.loc.locator(".shiny-chat-page-main")
        self.loc_body = self.loc.locator(".shiny-chat-page-body")
        self.loc_identity = self.loc.locator(".shiny-chat-page-identity")
        self.loc_identity_title = self.loc.locator(
            ".shiny-chat-page-identity-title"
        )
        self.loc_toolbar = self.loc.locator(".shiny-chat-page-toolbar")
        self.loc_controls = self.loc.locator(".shiny-chat-page-controls")
        self.loc_controls_mount_desktop = self.loc.locator(
            ".shiny-chat-page-controls-mount-desktop"
        )
        self.loc_controls_mount_mobile = self.loc.locator(
            ".shiny-chat-page-controls-mount-mobile"
        )

    # ------------------------------------------------------------------
    # Active page
    # ------------------------------------------------------------------

    @property
    def active_page(self) -> str:
        """The current ``data-active-page`` attribute value."""
        return self.loc.get_attribute("data-active-page") or "__home__"

    def expect_active_page(
        self,
        value: str,
        *,
        timeout: Timeout = None,
    ) -> None:
        """
        Expects the active page to be the given value.

        Parameters
        ----------
        value
            The expected page value (use ``"__home__"`` for the chat home).
        timeout
            The maximum time to wait for the expectation to pass.
        """
        playwright_expect(self.loc).to_have_attribute(
            "data-active-page", value, timeout=timeout
        )

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------

    def select_page(
        self,
        name: str,
        *,
        exact: bool = False,
    ) -> None:
        """
        Clicks a nav button by accessible name.

        Parameters
        ----------
        name
            The accessible name of the nav button to click.
        exact
            Whether to match the name exactly. Defaults to ``False``.
        """
        self.loc_nav.get_by_role("button", name=name, exact=exact).click()

    def return_home(self) -> None:
        """Clicks the ``Return to chat`` button to navigate to the chat home."""
        self.loc.get_by_role("button", name="Return to chat").click()

    def open_nav_offcanvas(
        self,
        *,
        timeout: Timeout = None,
    ) -> None:
        """
        Open the offcanvas hosting nav-driving action buttons.

        Clicks the app's ``#nav_controls`` button and waits for the
        offcanvas panel to appear.  Only works for test apps that include
        this pattern (e.g. the page-chat test app's programmatic
        navigation controls).
        """
        self.page.locator("#nav_controls").click()
        self.page.wait_for_selector(
            ".offcanvas.show",
            timeout=timeout if timeout is not None else _DEFAULT_TIMEOUT,
        )

    # ------------------------------------------------------------------
    # Sidebar / mobile app menu
    # ------------------------------------------------------------------

    def expect_sidebar_open(
        self,
        *,
        timeout: Timeout = None,
    ) -> None:
        """
        Expects the sidebar to be visible.

        Parameters
        ----------
        timeout
            The maximum time to wait for the expectation to pass.
        """
        playwright_expect(self.loc_sidebar).to_be_visible(timeout=timeout)

    def expect_sidebar_closed(
        self,
        *,
        timeout: Timeout = None,
    ) -> None:
        """
        Expects the sidebar to be hidden.

        Parameters
        ----------
        timeout
            The maximum time to wait for the expectation to pass.
        """
        playwright_expect(self.loc_sidebar).to_be_hidden(timeout=timeout)

    def open_sidebar(self) -> None:
        """Opens the sidebar (desktop) or app menu (mobile) if not already open."""
        if self.loc_sidebar_toggle.get_attribute("aria-expanded") != "true":
            self.loc_sidebar_toggle.click()

    def close_sidebar(self) -> None:
        """Closes the sidebar (desktop) or app menu (mobile) if not already closed."""
        if self.loc_sidebar_toggle.get_attribute("aria-expanded") == "true":
            self.loc_sidebar_toggle.click()

    def expect_mobile_menu_open(
        self,
        *,
        timeout: Timeout = None,
    ) -> None:
        """
        Expects the mobile app menu to be open.

        Parameters
        ----------
        timeout
            The maximum time to wait for the expectation to pass.
        """
        playwright_expect(self.loc).to_have_attribute(
            "data-mobile-menu-open", "true", timeout=timeout
        )

    def expect_mobile_menu_closed(
        self,
        *,
        timeout: Timeout = None,
    ) -> None:
        """
        Expects the mobile app menu to be closed.

        The application removes ``data-mobile-menu-open`` entirely when
        the menu closes.  Playwright's ``not_to_have_attribute`` cannot
        distinguish "absent" from "present with an empty value" because
        it substitutes an empty string for missing attributes, so this
        polls for genuine attribute absence instead.

        Parameters
        ----------
        timeout
            The maximum time to wait for the expectation to pass.
        """
        self.page.wait_for_function(
            (
                "(selector) => {"
                " const el = document.querySelector(selector);"
                " return el && !el.hasAttribute('data-mobile-menu-open');"
                " }"
            ),
            arg=f'shiny-chat-page[data-chat-id="{self.id}"]',
            timeout=timeout if timeout is not None else _DEFAULT_TIMEOUT,
        )

    def open_mobile_menu(self) -> None:
        """Opens the mobile app menu if not already open."""
        if self.loc.get_attribute("data-mobile-menu-open") is not None:
            return
        self.loc_sidebar_toggle.click()

    def close_mobile_menu(self) -> None:
        """Closes the mobile app menu if currently open."""
        if self.loc.get_attribute("data-mobile-menu-open") is not None:
            self.page.keyboard.press("Escape")
