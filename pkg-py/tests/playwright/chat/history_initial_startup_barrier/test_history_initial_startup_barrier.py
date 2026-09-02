from __future__ import annotations

import re

import pytest
from playwright.sync_api import Page, expect
from shiny.playwright import controller
from shiny.run import ShinyAppProc


def test_browser_no_target_releases_constructor_and_startup_append(
    page: Page, local_app: ShinyAppProc
) -> None:
    page.goto(local_app.url)

    messages = page.locator(".shiny-chat-message, .shiny-chat-user-message")
    expect(messages).to_have_count(2, timeout=30_000)
    expect(messages.nth(0)).to_contain_text("constructor message")
    expect(messages.nth(1)).to_contain_text("startup append")
    controller.OutputText(page, "startup_exchange").expect_value(
        re.compile(r'"messages": \["startup append"\]'),
        timeout=30_000,
    )


@pytest.mark.parametrize("local_app", ["app_url.py"], indirect=True)
def test_url_target_suppresses_constructor_and_targets_startup_append(
    page: Page, local_app: ShinyAppProc
) -> None:
    page.goto(f"{local_app.url}?shinychat_conversation_id=startup-target")

    messages = page.locator(".shiny-chat-message, .shiny-chat-user-message")
    expect(messages).to_have_count(2, timeout=30_000)
    expect(messages.nth(0)).to_contain_text("restored input")
    expect(messages.nth(1)).to_contain_text("startup append")
    expect(page.get_by_text("constructor message", exact=True)).to_have_count(0)
    controller.OutputText(page, "startup_exchange").expect_value(
        re.compile(
            r'"active_id": "n_0002", "parent_id": "n_0001", '
            r'"messages": \["startup append"\]'
        ),
        timeout=30_000,
    )
