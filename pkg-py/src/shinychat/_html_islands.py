from __future__ import annotations

from htmltools import Tag, TagChild, TagList


def _has_react_attr(child: TagChild) -> bool:
    """Check if a tag child has the data-shinychat-react attribute."""
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
    else:
        return [Tag("shinychat-html", content)]

    from itertools import groupby

    result: list[TagChild] = []
    for is_react, group in groupby(children, _has_react_attr):
        if is_react:
            result.extend(group)
        else:
            result.append(Tag("shinychat-html", *group))
    return result
