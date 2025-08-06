try:
    import playwright  # noqa: F401 # pyright: ignore[reportUnusedImport, reportMissingTypeStubs]
except ImportError:
    raise ImportError(
        "The shinychat.playwright module requires the playwright package to be installed. "
        "Please install it with: `pip install playwright`"
    )

# If `pytest` is installed...
try:
    import pytest  # noqa: F401 # pyright: ignore[reportUnusedImport, reportMissingTypeStubs]

    # At this point, `playwright` and `pytest` are installed.
    # Try to make sure `pytest-playwright` is installed
    try:
        import pytest_playwright  # noqa: F401 # pyright: ignore[reportUnusedImport, reportMissingTypeStubs]

    except ImportError:
        raise ImportError(
            "If you are using pytest to test your shiny app, install the pytest-playwright "
            "shim package with: `pip install pytest-playwright`"
        )
except ImportError:
    pass

from ._chat import Chat as ChatController

__all__ = ["ChatController"]
