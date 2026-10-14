from htmltools import tags
from shinychat._chat_segments import (
    StreamSegment,
    append_chunk_segments,
    append_to_segments,
    has_mixed_content_types,
    segments_content,
)
from shinychat._chat_types import ChatMessage, ContentSegment, is_html_block


def test_append_merges_same_content_type():
    segs: list[ContentSegment] = []
    append_to_segments(segs, "a", "markdown")
    append_to_segments(segs, "b", "markdown")
    assert len(segs) == 1
    assert isinstance(segs[0], ContentSegment)
    assert segs[0].content == "ab"


def test_append_splits_on_content_type_change():
    segs: list[ContentSegment] = []
    append_to_segments(segs, "a", "markdown")
    append_to_segments(segs, "t", "thinking")
    append_to_segments(segs, "b", "markdown")
    assert all(isinstance(s, ContentSegment) for s in segs)
    assert [s.content_type for s in segs] == [
        "markdown",
        "thinking",
        "markdown",
    ]


def test_segments_content_concatenates():
    segs: list[ContentSegment] = []
    append_to_segments(segs, "a", "markdown")
    append_to_segments(segs, "t", "thinking")
    assert segments_content(segs) == "at"


def test_has_mixed_content_types():
    segs: list[ContentSegment] = []
    append_to_segments(segs, "a", "markdown")
    assert has_mixed_content_types(segs) is False
    append_to_segments(segs, "t", "thinking")
    assert has_mixed_content_types(segs) is True


def test_append_chunk_segments_strings_coalesce_blocks_append():
    segs: list[StreamSegment] = []
    append_chunk_segments(segs, ChatMessage("a"), lambda deps: None)
    append_chunk_segments(segs, ChatMessage("b"), lambda deps: None)
    append_chunk_segments(
        segs, ChatMessage(tags.div("card")), lambda deps: None
    )

    assert len(segs) == 2
    assert isinstance(segs[0], ContentSegment)
    assert segs[0].content == "ab"
    assert isinstance(segs[1], dict) and is_html_block(segs[1])
    assert segs[1]["content"] == "<div>card</div>"
