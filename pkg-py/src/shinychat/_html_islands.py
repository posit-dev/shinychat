from __future__ import annotations

from itertools import groupby

from htmltools import Tag, TagChild, Tagifiable, TagList


def _resolve_tagifiable(content: TagChild) -> TagChild:
    """Resolve a Tagifiable to its Tag form (if it isn't already a Tag/TagList/str)."""
    if isinstance(content, (Tag, TagList, str)):
        return content
    if isinstance(content, Tagifiable):
        return content.tagify()
    return content


def _has_react_attr(child: TagChild) -> bool:
    """Check if a tag child has the data-shinychat-react attribute."""
    child = _resolve_tagifiable(child)
    if isinstance(child, Tag):
        return "data-shinychat-react" in child.attrs
    return False


def split_html_islands(content: TagChild | TagList) -> list[TagChild]:
    """
    Split tag content around elements with data-shinychat-react.

    Elements WITH the attribute are emitted bare.
    Consecutive elements WITHOUT the attribute are grouped into
    <shinychat-html> wrappers.

    Returns a list of TagChild items ready to be serialized.
    """
    if isinstance(content, TagList):
        children = list(content)
    elif isinstance(content, Tag):
        if _has_react_attr(content):
            return [content]
        return [Tag("shinychat-html", content)]
    elif isinstance(content, Tagifiable):
        resolved = content.tagify()
        if isinstance(resolved, Tag) and _has_react_attr(resolved):
            return [resolved]
        return [Tag("shinychat-html", content)]
    else:
        return [Tag("shinychat-html", content)]

    result: list[TagChild] = []
    for is_react, group in groupby(children, _has_react_attr):
        if is_react:
            result.extend(group)
        else:
            result.append(Tag("shinychat-html", *group))
    return result
