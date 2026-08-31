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


@dataclass
class IslandBlockPart:
    """A run of trusted non-React content's rendered HTML and dependencies."""

    html: str
    deps: list[HTMLDependency]


@dataclass
class IslandResidualPart:
    """A run of bare `data-shinychat-react` elements' rendered HTML and dependencies."""

    html: str
    deps: list[HTMLDependency]


IslandPart = Union[IslandBlockPart, IslandResidualPart]


def derive_island_parts(content: TagChild | TagList) -> list[IslandPart]:
    """
    Partition trusted tag content around `data-shinychat-react` elements.

    Runs without the attribute become `IslandBlockPart` parts (trusted HTML
    + deps → `html_block` envelopes). Elements with the attribute become
    `IslandResidualPart` string runs. This is the single derivation shared
    by `ChatMessage` and `MarkdownStream`; no wrapper tag is constructed.
    """
    if isinstance(content, (TagList, TagifiedTagList)):
        children: list[TagChild] = list(content)
    else:
        children = [content]

    parts: list[IslandPart] = []
    for is_react, group in groupby(children, _has_react_attr):
        if is_react:
            for item in group:
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
        else:
            island = TagList(*group).render()
            parts.append(
                IslandBlockPart(
                    html=island["html"], deps=list(island["dependencies"])
                )
            )
    return parts
