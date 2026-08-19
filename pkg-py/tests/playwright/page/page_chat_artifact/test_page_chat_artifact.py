import pytest
from playwright.sync_api import Locator, Page, expect
from shiny.run import ShinyAppProc
from shinychat.playwright import ChatController

TIMEOUT = 30_000


def open_page(
    page: Page, local_app: ShinyAppProc
) -> tuple[ChatController, Locator]:
    page.set_viewport_size({"width": 1440, "height": 900})
    page.goto(local_app.url)
    chat = ChatController(page, "chat")
    shell = page.locator("shiny-chat-page")
    expect(shell).to_be_visible(timeout=TIMEOUT)
    expect(chat.loc).to_be_visible(timeout=TIMEOUT)
    return chat, shell


def test_percentage_artifact_keeps_desktop_chat_width(
    page: Page, local_app: ShinyAppProc
) -> None:
    chat, _ = open_page(page, local_app)
    page.get_by_role("button", name="Show artifact").click()

    panel = chat.loc.locator(".shiny-chat-artifact")
    layout = chat.loc.locator(".shiny-chat-layout")
    wrapper = chat.loc.locator(".shiny-chat-wrapper")
    expect(panel).to_be_visible(timeout=TIMEOUT)
    page.wait_for_timeout(220)

    layout_box = layout.bounding_box()
    panel_box = panel.bounding_box()
    wrapper_box = wrapper.bounding_box()
    assert layout_box is not None
    assert panel_box is not None
    assert wrapper_box is not None
    assert panel_box["width"] > 0
    assert wrapper_box["width"] >= 360
    assert panel_box["x"] >= layout_box["x"] + wrapper_box["width"]

    grid_tracks = layout.evaluate(
        """(element) =>
          getComputedStyle(element).gridTemplateColumns
            .split(" ")
            .map((value) => Number.parseFloat(value))"""
    )
    assert isinstance(grid_tracks, list)
    assert len(grid_tracks) == 2
    assert grid_tracks[0] >= 360
    assert wrapper_box["width"] <= grid_tracks[0] + 1
    assert panel_box["width"] == pytest.approx(grid_tracks[1], abs=1)

    separator = page.get_by_role("separator", name="Resize artifact panel")
    expect(separator).to_be_visible()
    minimum = int(separator.get_attribute("aria-valuemin") or "0")
    maximum = int(separator.get_attribute("aria-valuemax") or "0")
    current = int(separator.get_attribute("aria-valuenow") or "0")
    assert minimum == 240
    assert minimum <= current <= maximum
    expect(separator).to_have_attribute("aria-valuetext", f"{current} pixels")


def test_page_artifact_survives_navigation_and_history(
    page: Page, local_app: ShinyAppProc
) -> None:
    chat, shell = open_page(page, local_app)
    panel = chat.loc.locator(".shiny-chat-artifact")

    page.get_by_role("button", name="Show artifact").click()
    expect(panel).to_be_visible(timeout=TIMEOUT)
    expect(panel.get_by_role("heading")).to_have_text("Initial artifact")

    page.get_by_role("button", name="Update artifact").click()
    expect(panel.get_by_role("heading")).to_have_text("Updated artifact")
    artifact_input = panel.locator("#artifact_text")
    artifact_input.fill("edited artifact")
    expect(panel.locator("#artifact_value")).to_have_text(
        "Artifact value: edited artifact",
        timeout=TIMEOUT,
    )

    shell.get_by_role("button", name="Details").click()
    expect(shell).to_have_attribute("data-active-page", "details")
    expect(chat.loc).to_be_hidden()
    expect(panel).to_be_hidden()
    expect(page.locator("#details_page")).to_be_visible()

    shell.get_by_role("button", name="Return to chat").click()
    expect(chat.loc).to_be_visible()
    expect(panel).to_be_visible()
    expect(artifact_input).to_have_value("edited artifact")
    expect(panel.locator("#artifact_value")).to_have_text(
        "Artifact value: edited artifact",
        timeout=TIMEOUT,
    )

    chat.set_user_input("first conversation")
    chat.send_user_input()
    chat.expect_latest_message("echo: first conversation", timeout=TIMEOUT)

    sidebar = shell.locator(".shiny-chat-page-sidebar")
    toggle = shell.locator(".shiny-chat-page-sidebar-toggle")
    expect(sidebar).to_be_hidden()
    toggle.click()
    expect(sidebar).to_be_visible()
    expect(sidebar.locator(".shiny-chat-history-item")).to_have_count(
        1, timeout=TIMEOUT
    )

    sidebar.locator(".shiny-chat-history-new").click()
    expect(chat.loc_messages.locator("> *")).to_have_count(0, timeout=TIMEOUT)
    expect(panel).to_be_visible()
    expect(artifact_input).to_have_value("edited artifact")

    chat.set_user_input("second conversation")
    chat.send_user_input()
    chat.expect_latest_message("echo: second conversation", timeout=TIMEOUT)
    expect(sidebar.locator(".shiny-chat-history-item")).to_have_count(
        2, timeout=TIMEOUT
    )

    sidebar.locator(
        ".shiny-chat-history-item-select", has_text="first conversation"
    ).click()
    chat.expect_latest_message("echo: first conversation", timeout=TIMEOUT)
    expect(panel).to_be_visible()
    expect(panel.get_by_role("heading")).to_have_text("Updated artifact")
    expect(artifact_input).to_have_value("edited artifact")
    expect(panel.locator("#artifact_value")).to_have_text(
        "Artifact value: edited artifact",
        timeout=TIMEOUT,
    )


def test_artifact_motion_retains_close_panel_and_suppresses_resize(
    page: Page, local_app: ShinyAppProc
) -> None:
    chat, _ = open_page(page, local_app)
    layout = chat.loc.locator(".shiny-chat-layout")
    panel = chat.loc.locator(".shiny-chat-artifact")

    assert "--shiny-chat-artifact-layout-width" in layout.evaluate(
        "(element) => getComputedStyle(element).transitionProperty"
    )
    page.locator("#show_artifact").click()
    expect(panel).to_have_attribute("data-motion", "open")
    expect(layout).to_have_attribute("data-artifact-open", "")

    separator = page.get_by_role("separator", name="Resize artifact panel")
    separator.dispatch_event("resize-start")
    expect(layout).to_have_attribute("data-artifact-resizing", "")
    expect(layout).to_have_css("transition-duration", "0s")

    panel.get_by_role("button", name="Close artifact").click()
    expect(panel).to_have_attribute("data-motion", "closing")
    expect(layout).not_to_have_attribute("data-artifact-resizing", "")
    expect(panel).to_have_attribute("aria-hidden", "true")
    assert panel.evaluate("(element) => element.hidden") is False
    expect(layout).to_have_attribute("data-artifact-open", "")
    expect(panel).to_be_hidden(timeout=TIMEOUT)
    expect(layout).not_to_have_attribute("data-artifact-open", "")


def test_artifact_layout_track_interpolates_during_desktop_reveal(
    page: Page, local_app: ShinyAppProc
) -> None:
    chat, _ = open_page(page, local_app)
    layout = chat.loc.locator(".shiny-chat-layout")
    panel = chat.loc.locator(".shiny-chat-artifact")

    page.locator("#show_artifact").click()
    expect(layout).to_have_attribute("data-artifact-open", "")
    expect(panel).to_be_visible()
    page.wait_for_timeout(70)
    intermediate_track = layout.evaluate(
        """(element) =>
          Number.parseFloat(
            getComputedStyle(element).gridTemplateColumns.split(" ")[1]
          )"""
    )
    page.wait_for_timeout(220)
    final_track = layout.evaluate(
        """(element) =>
          Number.parseFloat(
            getComputedStyle(element).gridTemplateColumns.split(" ")[1]
          )"""
    )

    assert intermediate_track > 0
    assert intermediate_track < final_track


def test_artifact_motion_respects_reduced_motion_and_takeover(
    page: Page, local_app: ShinyAppProc
) -> None:
    page.emulate_media(reduced_motion="reduce")
    chat, _ = open_page(page, local_app)
    layout = chat.loc.locator(".shiny-chat-layout")
    panel = chat.loc.locator(".shiny-chat-artifact")

    page.get_by_role("button", name="Show artifact").click()
    expect(layout).to_have_css("transition-duration", "0s")
    expect(panel).to_have_css("transition-duration", "0s")

    panel.get_by_role("button", name="Close artifact").click()
    expect(panel).to_be_hidden(timeout=TIMEOUT)

    page.emulate_media(reduced_motion="no-preference")
    page.set_viewport_size({"width": 1024, "height": 900})
    page.locator("#show_artifact").click()
    expect(layout).to_have_attribute("data-artifact-takeover", "")
    expect(layout).to_have_css("transition-duration", "0s")
