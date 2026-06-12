from shiny.express import ui
from shinychat.express import Chat

chat = Chat("chat")
chat.ui(placeholder="Type / for commands...")

ui.tags.div(id="slash_output")

# Client-side command: handled entirely in JS via shiny:chat-slash-command
_remove_ping = chat.slash_command("ping", "Client-side ping", fn=None)

# Side-effect-only server command: runs server-side but not echoed/stored
@chat.slash_command("note", "Side-effect only", echo=False)
async def _():
    ui.notification_show("noted")


@chat.slash_command("greet", "Send a greeting")
async def _(user_input: str):
    await chat.append_message(f"Hello! You said: {user_input}")


@chat.slash_command("clear", "Clear the chat")
async def _():
    await chat.clear_messages()


@chat.on_user_submit
async def _():
    user_input = chat.user_input()
    assert user_input is not None
    text, _ = user_input
    await chat.append_message(f"Echo: {text}")


ui.tags.script(
    """
    document.addEventListener('shiny:chat-slash-command', (e) => {
      if (e.detail.command === 'ping') {
        e.preventDefault();
        e.detail.echo = true;
      }
    });
    """
)
