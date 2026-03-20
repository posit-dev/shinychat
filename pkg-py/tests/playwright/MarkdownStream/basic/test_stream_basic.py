from playwright.sync_api import Page, expect
from shiny.playwright import controller
from shiny.run import ShinyAppProc


def test_validate_stream_basic(page: Page, local_app: ShinyAppProc) -> None:
    page.goto(local_app.url)

    stream = page.locator("#shiny_readme")
    expect(stream).to_be_visible(timeout=30 * 1000)
    expect(stream).to_contain_text("pip install shiny")

    # Check that the card body container (the parent of the markdown stream) is scrolled
    # all the way to the bottom. Smooth scrolling may still be animating, so poll until done.
    page.wait_for_function(
        """(selector) => {
            const el = document.querySelector(selector);
            if (!el) return false;
            const scrollTop = Math.round(el.scrollTop);
            const scrollHeight = Math.round(el.scrollHeight);
            const clientHeight = Math.round(el.clientHeight);
            if (scrollHeight <= clientHeight) return false;
            return Math.abs((scrollTop + clientHeight) - scrollHeight) <= 1;
        }""",
        arg=".card-body",
        timeout=5000,
    )

    stream2 = page.locator("#shiny_readme_err")
    expect(stream2).to_be_visible(timeout=30 * 1000)
    expect(stream2).to_contain_text("Shiny")

    notification = page.locator(".shiny-notification-error")
    expect(notification).to_be_visible(timeout=30 * 1000)
    expect(notification).to_contain_text("boom!")

    txt_result = controller.OutputText(page, "stream_result")
    txt_result.expect_value("Stream result: Basic stream")
