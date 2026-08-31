from __future__ import annotations

from dataclasses import dataclass
from itertools import groupby
from typing import Union

from htmltools import (
    HTML,
    HTMLDependency,
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
        return not (isinstance(child, str) and not isinstance(child, HTML))

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


@dataclass
class IslandBlockPart:
    """
    A `<shiny-chat-raw-html>` island wrapper's rendered payload: the trusted
    children HTML (an `html_block`'s `content`), plus the dependency objects
    the island carries.
    """

    html: str
    deps: list[HTMLDependency]


@dataclass
class IslandResidualPart:
    """
    A run of bare `data-shinychat-react` elements: rendered HTML surrounded
    by blank lines (so the markdown parser treats block-level custom
    elements correctly), plus the dependency objects the run carries.
    """

    html: str
    deps: list[HTMLDependency]


# One derived piece of trusted content: an island payload (becomes a
# structured `html_block`) or a residual string run (stays a trusted string
# segment).
IslandPart = Union[IslandBlockPart, IslandResidualPart]


def derive_island_parts(content: TagChild | TagList) -> list[IslandPart]:
    """
    Walk `split_html_islands()` output: island wrappers
    (`<shiny-chat-raw-html>`) become `IslandBlockPart` parts (rendered
    children HTML + dependency objects); bare `data-shinychat-react`
    elements become `IslandResidualPart` string runs (rendered bare,
    surrounded by blank lines, adjacent runs coalesced).

    This is the single derivation shared by `ChatMessage` (message content)
    and `MarkdownStream` (stream/output emission) so trusted non-string
    content becomes `html_block` envelopes identically everywhere. See
    kata#mhyd.
    """
    parts: list[IslandPart] = []
    for item in split_html_islands(content):
        if isinstance(item, (Tag, TagifiedTag)) and (
            item.name == "shiny-chat-raw-html"
        ):
            # Island wrapper: render its children (not the wrapper itself)
            # as the block's trusted HTML content.
            island = TagList(*item.children).render()
            parts.append(
                IslandBlockPart(
                    html=island["html"], deps=list(island["dependencies"])
                )
            )
        else:
            # Bare React element: render it bare and keep it as a residual
            # string run, surrounded by blank lines so the markdown parser
            # treats block-level custom elements correctly.
            rendered = TagList(item).render()
            run = f"\n\n{rendered['html']}\n\n"
            if parts and isinstance(parts[-1], IslandResidualPart):
                parts[-1].html += run
                parts[-1].deps.extend(rendered["dependencies"])
            else:
                parts.append(
                    IslandResidualPart(
                        html=run, deps=list(rendered["dependencies"])
                    )
                )
    return parts
