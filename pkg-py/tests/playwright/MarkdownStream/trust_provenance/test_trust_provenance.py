from playwright.sync_api import Page, expect
from shiny.playwright import controller
from shiny.run import ShinyAppProc


def test_mixed_stream_preserves_provenance(
    page: Page, local_app: ShinyAppProc
) -> None:
    page.goto(local_app.url)

    stream = page.locator("#stream")
    expect(stream).to_contain_text("<shiny-chat-raw-html>", timeout=30_000)
    expect(stream.locator("[data-forged]")).to_have_count(0)
    assert page.evaluate("window.__forgedFired ?? null") is None

    expect(stream.locator("h2")).to_have_text("This is markdown")
    button = controller.InputActionButton(page, "trusted_btn")
    expect(button.loc).to_be_visible()
