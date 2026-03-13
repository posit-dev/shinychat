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


def shinychat_dependency() -> HTMLDependency:
    return HTMLDependency(
        name="shinychat",
        version=__version__,
        source={
            "package": "shinychat",
            "subdir": "www",
        },
        script={"src": "shinychat.js", "type": "module"},
        stylesheet={"href": "shinychat.css"},
    )
