import asyncio

from shiny import App, reactive, ui  # noqa: I001
from shinychat import Chat, chat_greeting, chat_ui

GREETING_CONTENT = """\
## Welcome to the Explainer

Ask me about programming and data science concepts.

**Try one of these:**

- <span class="suggestion">What is a closure?</span>
- <span class="suggestion">Explain tidy evaluation</span>
- <span class="suggestion">How does gradient descent work?</span>
"""

GREETING_CONTENT_2 = """\
## Welcome Back

Here are some more topics to explore.

**Try one of these:**

- <span class="suggestion">What is recursion?</span>
- <span class="suggestion">Explain MapReduce</span>
- <span class="suggestion">How do neural networks learn?</span>
"""

app_ui = ui.page_fillable(
    ui.card(
        ui.card_header(
            "Greeting test app",
            ui.toolbar(
                ui.toolbar_input_button("clear_chat", "Clear"),
                ui.toolbar_input_button("clear_chat_and_greeting", "Reset"),
                align="right",
            ),
        ),
        chat_ui("chat", placeholder="Ask me anything...", fill=True),
    ),
)


def server(input, output, session):
    greeting_count = reactive.value(0)

    chat = Chat(id="chat")

    @chat.on_user_submit
    async def _(user_input: str):
        await asyncio.sleep(0.05)
        await chat.append_message(f"You said: {user_input}")

    @reactive.effect
    @reactive.event(input.chat_greeting_requested)
    async def _generate_greeting():
        count = greeting_count() + 1
        greeting_count.set(count)
        content = GREETING_CONTENT if count % 2 == 1 else GREETING_CONTENT_2

        async def stream():
            for line in content.split("\n"):
                await asyncio.sleep(0.01)
                yield line + "\n"

        await chat.set_greeting(chat_greeting(stream()))

    @reactive.effect
    @reactive.event(input.clear_chat)
    async def _clear_chat():
        await chat.clear_messages()

    @reactive.effect
    @reactive.event(input.clear_chat_and_greeting)
    async def _clear_chat_and_greeting():
        await chat.clear_messages(greeting=True)


app = App(app_ui, server)
