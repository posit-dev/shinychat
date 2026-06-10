from playwright.sync_api import Page, expect
from shiny.run import ShinyAppProc
from shinychat.playwright import ChatController


def test_stage_attachment_appears_in_input(
    page: Page, local_app: ShinyAppProc
) -> None:
    page.goto(local_app.url)
    chat = ChatController(page, "chat")
    expect(chat.loc).to_be_visible(timeout=30_000)

    page.locator("#stage").click()

    # A thumbnail should appear; textarea text is unchanged (empty).
    thumb = page.locator(".shiny-chat-input-thumbnail")
    expect(thumb).to_have_count(1)
    chat.expect_user_input("")
    # Send button enabled because there is a staged attachment.
    expect(chat.loc_input_button).to_be_enabled()


def test_stage_and_submit_sends_attachment(
    page: Page, local_app: ShinyAppProc
) -> None:
    page.goto(local_app.url)
    chat = ChatController(page, "chat")
    expect(chat.loc).to_be_visible(timeout=30_000)

    page.locator("#stage_and_submit").click()

    # The message was submitted with the attachment.
    chat.expect_latest_message("Got 1 attachment(s).")
    # Input and staging area are cleared after submit.
    chat.expect_user_input("")
    expect(page.locator(".shiny-chat-input-thumbnail")).to_have_count(0)


def test_append_mode_adds_to_existing(
    page: Page, local_app: ShinyAppProc
) -> None:
    page.goto(local_app.url)
    chat = ChatController(page, "chat")
    expect(chat.loc).to_be_visible(timeout=30_000)

    # Stage the first attachment (image).
    page.locator("#stage").click()
    # Count staged items via the container's direct children (covers all
    # attachment types: image thumbnails, text previews, chips).
    staged = page.locator(".shiny-chat-input-attachments > *")
    expect(staged).to_have_count(1)

    # Append a second attachment (text file) — default mode is "append".
    page.locator("#append").click()
    expect(staged).to_have_count(2)


def test_set_mode_replaces_existing(
    page: Page, local_app: ShinyAppProc
) -> None:
    page.goto(local_app.url)
    chat = ChatController(page, "chat")
    expect(chat.loc).to_be_visible(timeout=30_000)

    # Stage the first attachment (image).
    page.locator("#stage").click()
    staged = page.locator(".shiny-chat-input-attachments > *")
    expect(staged).to_have_count(1)

    # Set-replace replaces with a text file — still exactly one item.
    page.locator("#set_replace").click()
    expect(staged).to_have_count(1)


def test_append_on_submit_includes_staged(
    page: Page, local_app: ShinyAppProc
) -> None:
    page.goto(local_app.url)
    chat = ChatController(page, "chat")
    expect(chat.loc).to_be_visible(timeout=30_000)

    # Stage one attachment first.
    page.locator("#stage").click()
    expect(page.locator(".shiny-chat-input-thumbnail")).to_have_count(1)

    # Append another and submit — both should arrive.
    page.locator("#append_and_submit").click()
    chat.expect_latest_message("Got 2 attachment(s).")
    # Input is cleared after submit.
    chat.expect_user_input("")
    expect(page.locator(".shiny-chat-input-thumbnail")).to_have_count(0)
