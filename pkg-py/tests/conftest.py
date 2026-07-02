import pytest


# Fix the anyio backend to asyncio (function-scoped) so each test gets an
# isolated event loop. Without this, anyio parametrizes on all available
# backends at module scope, which can cause loop-lifecycle conflicts in
# Python 3.11 when asyncio.run() or other loop-sensitive code runs in the
# same pytest session.
@pytest.fixture
def anyio_backend():
    return "asyncio"
