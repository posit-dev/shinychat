"""
OpenTelemetry instrumentation for managed chat responses.

One ``shinychat.response`` span per managed response, carrying
``gen_ai.conversation.id``, so downstream consumers (e.g. Posit Commons) can
attribute model work to a conversation. The span is active for the full
consumption of the response stream, so chatlas (or other client) spans nest
beneath it.

Tracing is strictly observational: with no SDK provider configured the spans
are non-recording no-ops, and any telemetry failure — tracer resolution,
span start, or span end — degrades to an untraced context, so tracing can
never break the model call.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, AsyncIterable, AsyncIterator, Iterator


@contextmanager
def response_span(conversation_id: str | None) -> Iterator[None]:
    """
    Context manager for a managed response's ``shinychat.response`` span.

    Yields an untraced context when there is no conversation ID (history
    disabled or empty draft) or when OpenTelemetry is unavailable or fails
    at any point — tracer resolution, span start, or span end.
    """
    if conversation_id is None:
        yield
        return
    try:
        from opentelemetry import trace
    except ImportError:
        yield
        return
    try:
        # Resolved fresh per response: a tracer cached at import time would
        # still delegate dynamically (the OTel API returns a proxy tracer),
        # but resolving here keeps failure isolation trivial.
        tracer = trace.get_tracer("shinychat")
        span_cm = tracer.start_as_current_span(
            "shinychat.response",
            attributes={"gen_ai.conversation.id": conversation_id},
        )
        span_cm.__enter__()
    except Exception:
        yield
        return

    # Forward any exception from the wrapped work to the span's __exit__
    # (so the span records the error), and guard the exit itself: a failing
    # processor/exporter must not mask or break the model call.
    exc: BaseException | None = None
    try:
        yield
    except BaseException as e:
        exc = e
        raise
    finally:
        try:
            if exc is None:
                span_cm.__exit__(None, None, None)
            else:
                span_cm.__exit__(type(exc), exc, exc.__traceback__)
        except Exception:
            pass


async def trace_response_stream(
    stream: AsyncIterable[Any],
    conversation_id: str | None,
) -> AsyncIterator[Any]:
    """
    Wrap a managed response stream so its ``shinychat.response`` span stays
    active for the full consumption.

    ``Chat.append_message_stream()`` consumes streams in a background task,
    so a ``with response_span(...)`` block around the call site would close
    the span long before the stream finishes. Wrapping the generator instead
    opens the span when consumption begins (still before any model work —
    chatlas's ``stream_async()`` is lazy and does all provider I/O inside
    the generator) and closes it once the stream is exhausted or fails.

    ``conversation_id`` is captured as a scalar at submission time, so
    in-flight work is never relabeled by later history switches, new-chat
    actions, or client swaps.
    """
    if conversation_id is None:
        async for chunk in stream:
            yield chunk
        return
    with response_span(conversation_id):
        async for chunk in stream:
            yield chunk
