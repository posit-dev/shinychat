import pytest
from shinychat._history_title import fallback_title, generate_title


def test_fallback_title_truncates_first_user_message():
    turns = [{"role": "user", "content": "x" * 100}]
    t = fallback_title(turns)
    assert t == "x" * 47 + "..."


def test_fallback_title_chatlas_shape():
    turns = [
        {
            "role": "user",
            "contents": [{"content_type": "text", "text": "show me penguins"}],
        }
    ]
    assert fallback_title(turns) == "show me penguins"


def test_fallback_title_skips_non_user_and_empty_turns():
    turns = [
        {"role": "assistant", "content": "hi there"},
        {"role": "user", "content": ""},
        {"role": "user", "content": "real question"},
    ]
    assert fallback_title(turns) == "real question"


def test_fallback_title_empty():
    assert fallback_title([]) == "New chat"


@pytest.mark.anyio
async def test_generate_title_uses_custom_callable():
    async def titler(turns):
        return "  My   Title  "

    result = await generate_title(
        titler, None, [{"role": "user", "content": "q"}]
    )
    assert result == "My Title"


@pytest.mark.anyio
async def test_generate_title_supports_sync_callable():
    def titler(turns):
        return "Sync Title"

    assert await generate_title(titler, None, []) == "Sync Title"


@pytest.mark.anyio
async def test_generate_title_failure_returns_none():
    async def titler(turns):
        raise RuntimeError("boom")

    with pytest.warns(
        UserWarning, match="Conversation title generation failed"
    ):
        result = await generate_title(titler, None, [])
    assert result is None


@pytest.mark.anyio
async def test_generate_title_none_returning_fn_returns_none():
    def titler(turns):
        return None

    assert await generate_title(titler, None, []) is None


@pytest.mark.anyio
async def test_generate_title_none_fn_non_chatlas_client_returns_none():
    class NotChatlas: ...

    assert await generate_title(None, NotChatlas(), []) is None
