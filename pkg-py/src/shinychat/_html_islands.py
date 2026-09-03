from __future__ import annotations

from itertools import groupby

from htmltools import (
    Tag,
    TagChild,
    Tagifiable,
    TagifiedTag,
    TagifiedTagList,
    TagList,
)


def _resolve_tagifiable(content: TagChild) -> TagChild:
    """Resolve a Tagifiable to its Tag form (if it isn't already a Tag/TagList/str)."""
    if isinstance(content, (Tag, TagifiedTag, TagList, TagifiedTagList, str)):
        return content
    if isinstance(content, Tagifiable):
        return content.tagify()
    return content


def _has_react_attr(child: TagChild) -> bool:
    """Check if a tag child has the data-shinychat-react attribute."""
    child = _resolve_tagifiable(child)
    if isinstance(child, (Tag, TagifiedTag)):
        return "data-shinychat-react" in child.attrs
    return False


def split_content_by_trust(
    content: TagChild | TagList,
) -> list[tuple[bool, TagChild]]:
    """
    Split mixed content into ordered provenance runs.

    Plain strings may contain model output and are untrusted. HTML()-marked
    strings, Tags, and Tagifiable values are server-authored UI and trusted.
    """
    if isinstance(content, (TagList, TagifiedTagList)):
        children = list(content)
    else:
        children = [content]

    def is_trusted(child: TagChild) -> bool:
        return not isinstance(child, str)

    result: list[tuple[bool, TagChild]] = []
    for trusted, group_iter in groupby(children, is_trusted):
        group = list(group_iter)
        if trusted:
            result.append((True, TagList(*group)))
        else:
            result.append((False, "".join(str(child) for child in group)))
    return result


def split_html_islands(content: TagChild | TagList) -> list[TagChild]:
    """
    Split tag content around elements with data-shinychat-react.

    Elements WITH the attribute are emitted bare.
    Consecutive elements WITHOUT the attribute are grouped into
    <shiny-chat-raw-html> wrappers.

    Returns a list of TagChild items ready to be serialized.
    """
    if isinstance(content, (TagList, TagifiedTagList)):
        children = list(content)
    elif isinstance(content, (Tag, TagifiedTag)):
        if _has_react_attr(content):
            return [content]
        return [Tag("shiny-chat-raw-html", content)]
    elif isinstance(content, Tagifiable):
        resolved = content.tagify()
        if isinstance(resolved, (Tag, TagifiedTag)) and _has_react_attr(
            resolved
        ):
            return [resolved]
        return [Tag("shiny-chat-raw-html", content)]
    else:
        return [Tag("shiny-chat-raw-html", content)]

    result: list[TagChild] = []
    for is_react, group in groupby(children, _has_react_attr):
        if is_react:
            result.extend(group)
        else:
            result.append(Tag("shiny-chat-raw-html", *group))
    return result
