"""Session surface that Shiny's reactive core calls on test-only sessions.

Shiny's reactive core calls a handful of session methods that are not part of
the public :class:`shiny.Session` API but exist on it (or on its base class) all
the same:

* ``_restore_gate(priority)`` - the future an effect waits on while the session
  restores bookmarked state, or ``None`` to run now.
* ``_otel_reactive_update_span()`` - the session's current-cycle span, if any.
* ``_increment_busy_count()`` / ``_decrement_busy_count()`` - the session's busy
  period for the effect.
* ``_unhandled_error(error)`` - receives an error raised by an effect.

py-shiny 1.9 (py-shiny#2508, "concurrent effects") made the first two load
bearing. Each effect now runs in its own task, and an error raised while
preparing that task, such as a missing ``_restore_gate``, is reported to
``_unhandled_error()`` instead of failing the flush. A duck-typed test session
that lacks either method therefore makes every effect silently not run, and that
shows up later as an unrelated assertion failure rather than as the missing
method.

Inherit :class:`FakeSessionReactiveApi` in any test session double that registers
reactive effects. Fake sessions already implement the busy-count and error
methods themselves, since tests observe those calls; this base supplies the two
gate methods with the same no-op defaults as Shiny's ``Session``. Override them
in a double that simulates a restore in progress or records OpenTelemetry spans.
"""

from __future__ import annotations

import asyncio


class FakeSessionReactiveApi:
    """No-op defaults for the session methods Shiny's reactive core calls."""

    def _restore_gate(self, priority: int) -> asyncio.Future[None] | None:
        """No bookmark restore is in progress: effects may run immediately."""
        return None

    def _otel_reactive_update_span(self) -> object | None:
        """Test sessions have no OpenTelemetry cycle span."""
        return None
