"""A separate process using only the public worker API and a real chatlas client."""

import asyncio
import json
import sys
import time
from pathlib import Path
from typing import Any, cast

import chatlas
import httpx
from shiny.session import get_current_session
from shinychat import Conversation
from shinychat.types import ConversationPartition, FileConversationStore


def response(request: httpx.Request) -> httpx.Response:
    payload = json.loads(request.content)
    assert payload["messages"] == [
        {"role": "system", "content": "Worker summary"},
        {
            "role": "user",
            "content": [{"type": "text", "text": "Continue in worker"}],
        },
    ]
    return httpx.Response(
        200,
        json={
            "id": "worker-completion",
            "object": "chat.completion",
            "created": 1,
            "model": "test-model",
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": "Provider worker answer",
                    },
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": 1,
                "completion_tokens": 1,
                "total_tokens": 2,
            },
        },
    )


async def main():
    assert get_current_session() is None
    directory = Path(sys.argv[1])
    deadline = time.monotonic() + 15
    while not (directory / "disconnected").exists():
        if time.monotonic() >= deadline:
            raise TimeoutError("The Shiny session has not disconnected.")
        await asyncio.sleep(0.05)
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(response)
    ) as http:
        client = chatlas.ChatOpenAICompletions(
            model="test-model",
            api_key="unused",
            kwargs={"http_client": cast(Any, http)},
        )
        conversation = await Conversation.load(
            FileConversationStore(directory),
            ConversationPartition(chat_id="chat", scope="alice"),
            sys.argv[2],
            client=client,
        )
        assert client.system_prompt == "Initial instructions"
        assert [turn.text for turn in client.get_turns()] == [
            "original",
            "echo: original",
        ]
        async with conversation.exchange("Continue in worker"):
            client.system_prompt = "Worker summary"
            client.set_turns([])
            result = await client.chat_async(
                "Continue in worker", echo="none", stream=False
            )
            assert await result.get_content() == "Provider worker answer"
            await conversation.append_message("Saved **worker** answer")
            conversation.values["deputy"] = {
                "version": 1,
                "run_id": "run-worker",
            }


if __name__ == "__main__":
    asyncio.run(main())
