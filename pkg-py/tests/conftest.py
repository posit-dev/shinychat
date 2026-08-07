import pytest


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    # The session-scoped sync Playwright loop must start after AnyIO tests finish.
    unit = [item for item in items if "playwright" not in item.path.parts]
    browser = [item for item in items if "playwright" in item.path.parts]
    items[:] = [*unit, *browser]


# Fix the anyio backend to asyncio (function-scoped) so each test gets an
# isolated event loop. Without this, anyio parametrizes on all available
# backends at module scope, which can cause loop-lifecycle conflicts in
# Python 3.11 when asyncio.run() or other loop-sensitive code runs in the
# same pytest session.
@pytest.fixture
def anyio_backend():
    return "asyncio"
