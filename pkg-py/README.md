# shinychat

<a href="https://posit-dev.github.io/shinychat/py"><img src="https://posit-dev.github.io/shinychat/logo.svg" align="right" height="138" alt="shinychat for Python website" /></a>

Chat UI component for [Shiny for Python](https://shiny.posit.co/py/).

**Note:** shinychat is automatically installed with Shiny for Python and available as `shiny.ui.Chat` and `shiny.express.ui.Chat`. For complete instructions about creating chatbots please see the [Shiny for Python documentation](https://shiny.posit.co/py/docs/genai-chatbots.html).

## Installation

You can install shinychat from PyPI with:

```bash
uv pip install shinychat
```

Or, install the development version of shinychat from [GitHub](https://github.com/posit-dev/shinychat) with:

```bash
uv pip install git+https://github.com/posit-dev/shinychat.git
```

## Example

```r
from shiny.express import render, ui
from shinychat.express import Chat

# Set some Shiny page options
ui.page_opts(title="Hello Chat")

# Create a chat component, with an initial message
chat = Chat(
    id="chat",
    messages=[
        {"content": "Hello! How can I help you today?", "role": "assistant"},
    ],
)

# Display the chat
chat.ui()


# Define a callback to run when the user submits a message
@chat.on_user_submit
async def handle_user_input(user_input: str):
    await chat.append_message(f"You said: {user_input}")


"Message state:"


@render.code
def message_state():
    return str(chat.messages())
```
