import pytest
from shinychat._history_title import fallback_title_from_text, generate_title


def test_fallback_title_from_text_truncates_long_text():
    assert fallback_title_from_text("x" * 100) == "x" * 47 + "..."


def test_fallback_title_from_text_boundary():
    # At exactly MAX_FALLBACK_LEN the text passes through untouched; one
    # character more triggers the ellipsis.
    assert fallback_title_from_text("y" * 50) == "y" * 50
    assert fallback_title_from_text("y" * 51) == "y" * 47 + "..."


def test_fallback_title_from_text_squashes_whitespace():
    assert fallback_title_from_text("  what    is\tthis?  ") == "what is this?"


def test_fallback_title_from_text_empty_is_new_chat():
    assert fallback_title_from_text("") == "New chat"
    assert fallback_title_from_text("   ") == "New chat"


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
