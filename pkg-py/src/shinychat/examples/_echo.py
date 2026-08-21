"""Private, credential-free chat client for runnable examples."""

from typing import Any, AsyncGenerator
from unittest.mock import MagicMock

import chatlas
from chatlas import AssistantTurn, Turn


class EchoChatClient(chatlas.Chat):
    """A local chat client that replies with the submitted text."""

    def __init__(self) -> None:
        provider = MagicMock()
        provider.name = "local-echo"
        provider.model = "local-echo"
        super().__init__(provider)

    async def stream_async(
        self, *args: Any, **kwargs: Any
    ) -> AsyncGenerator[str, None]:  # type: ignore[override]
        user_input = str(args[0]) if args else ""
        response = f"The assistant replied to your message: {user_input}"
        self.add_turn(Turn(role="user", contents=user_input))
        self.add_turn(AssistantTurn(contents=response))

        async def stream() -> AsyncGenerator[str, None]:
            yield response

        return stream()
