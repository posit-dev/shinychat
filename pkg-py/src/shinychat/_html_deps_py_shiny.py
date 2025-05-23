from __future__ import annotations

from htmltools import HTMLDependency

from .__version import __version__

"""
HTML dependencies for internal dependencies such as dataframe.

For...
* External dependencies (e.g. jQuery, Bootstrap), see `shiny.ui._html_deps_external`
* Internal dependencies (e.g. dataframe), see `shiny.ui._html_deps_py_shiny`
* shinyverse dependencies (e.g. bslib, htmltools), see `shiny.ui._html_deps_shinyverse`
"""


def chat_deps() -> list[HTMLDependency]:
    dep = HTMLDependency(
        name="shinychat-chat",
        version=__version__,
        source={
            "package": "shinychat",
            "subdir": "www/chat",
        },
        script={"src": "chat.js", "type": "module"},
        stylesheet={"href": "chat.css"},
    )
    return [dep, markdown_stream_dependency()]


def markdown_stream_dependency() -> HTMLDependency:
    return HTMLDependency(
        name="shinychat-markdown",
        version=__version__,
        source={
            "package": "shinychat",
            "subdir": "www/markdown-stream",
        },
        script={"src": "markdown-stream.js", "type": "module"},
        stylesheet={"href": "markdown-stream.css"},
    )
