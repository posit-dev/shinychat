from shinychat._chat_segments import (
    append_to_segments,
    has_mixed_content_types,
    segments_content,
)
from shinychat._chat_types import ContentSegment


def test_append_merges_same_content_type():
    segs: list[ContentSegment] = []
    append_to_segments(segs, "a", "markdown")
    append_to_segments(segs, "b", "markdown")
    assert len(segs) == 1
    assert segs[0].content == "ab"


def test_append_splits_on_content_type_change():
    segs: list[ContentSegment] = []
    append_to_segments(segs, "a", "markdown")
    append_to_segments(segs, "t", "thinking")
    append_to_segments(segs, "b", "markdown")
    assert [s.content_type for s in segs] == ["markdown", "thinking", "markdown"]


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
