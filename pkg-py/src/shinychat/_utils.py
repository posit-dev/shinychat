from __future__ import annotations

import asyncio
import contextlib
import functools
import inspect
import random
import secrets
from typing import (
    Any,
    AsyncIterable,
    Awaitable,
    Callable,
    Generator,
    Iterable,
    TypeVar,
    cast,
)

from ._typing_extensions import ParamSpec, TypeGuard

CancelledError = asyncio.CancelledError


# ==============================================================================
# Misc utility functions
# ==============================================================================
def rand_hex(bytes: int) -> str:
    """
    Creates a random hexadecimal string of size `bytes`. The length in
    characters will be bytes*2.
    """
    format_str = "{{:0{}x}}".format(bytes * 2)
    return format_str.format(secrets.randbits(bytes * 8))


def drop_none(x: dict[str, Any]) -> dict[str, object]:
    return {k: v for k, v in x.items() if v is not None}


# Intended for use with json.load()'s object_hook parameter.
# Note also that object_hook is only called on dicts, not on lists, so this
# won't work for converting "top-level" lists to tuples
def lists_to_tuples(x: object) -> object:
    if isinstance(x, dict):
        x = cast("dict[str, object]", x)
        return {k: lists_to_tuples(v) for k, v in x.items()}
    elif isinstance(x, list):
        x = cast("list[object]", x)
        return tuple(lists_to_tuples(y) for y in x)
    else:
        # TODO: are there other mutable iterators that we want to make read only?
        return x


# ==============================================================================
# Private random stream
# ==============================================================================
def private_random_id(prefix: str = "", bytes: int = 3) -> str:
    if prefix != "" and not prefix.endswith("_"):
        prefix += "_"

    with private_seed():
        return prefix + rand_hex(bytes)


@contextlib.contextmanager
def private_seed() -> Generator[None, None, None]:
    state = random.getstate()
    global own_random_state  # noqa: PLW0603
    try:
        random.setstate(own_random_state)
        yield
    finally:
        own_random_state = random.getstate()
        random.setstate(state)


# Initialize random state for shiny's own private stream of randomness.
current_random_state = random.getstate()
random.seed(secrets.randbits(128))
own_random_state = random.getstate()
random.setstate(current_random_state)

# ==============================================================================
# Async-related functions
# ==============================================================================

R = TypeVar("R")  # Return type
P = ParamSpec("P")


def wrap_async(
    fn: Callable[P, R] | Callable[P, Awaitable[R]],
) -> Callable[P, Awaitable[R]]:
    """
    Given a synchronous function that returns R, return an async function that wraps the
    original function. If the input function is already async, then return it unchanged.
    """

    if is_async_callable(fn):
        return fn

    fn = cast(Callable[P, R], fn)

    @functools.wraps(fn)
    async def fn_async(*args: P.args, **kwargs: P.kwargs) -> R:
        return fn(*args, **kwargs)

    return fn_async


# This function should generally be used in this code base instead of
# `iscoroutinefunction()`.
def is_async_callable(
    obj: Callable[P, R] | Callable[P, Awaitable[R]],
) -> TypeGuard[Callable[P, Awaitable[R]]]:
    """
    Determine if an object is an async function.

    This is a more general version of `inspect.iscoroutinefunction()`, which only works
    on functions. This function works on any object that has a `__call__` method, such
    as a class instance.

    Returns
    -------
    :
        Returns True if `obj` is an `async def` function, or if it's an object with a
        `__call__` method which is an `async def` function.
    """
    if inspect.iscoroutinefunction(obj):
        return True
    if hasattr(obj, "__call__"):  # noqa: B004
        if inspect.iscoroutinefunction(obj.__call__):  # type: ignore
            return True

    return False


def wrap_async_iterable(
    x: Iterable[Any] | AsyncIterable[Any],
) -> AsyncIterable[Any]:
    """
    Given any iterable, return an async iterable. The async iterable will yield the
    values of the original iterable, but will also yield control to the event loop
    after each value. This is useful when you want to interleave processing with other
    tasks, or when you want to simulate an async iterable from a regular iterable.
    """

    if isinstance(x, AsyncIterable):
        return x

    if not isinstance(x, Iterable):
        raise TypeError("wrap_async_iterable requires an Iterable object.")

    return MakeIterableAsync(x)


class MakeIterableAsync:
    def __init__(self, iterable: Iterable[Any]):
        self.iterable = iterable

    def __aiter__(self):
        self.iterator = iter(self.iterable)
        return self

    async def __anext__(self):
        try:
            value = next(self.iterator)
            await asyncio.sleep(0)  # Yield control to the event loop
            return value
        except StopIteration:
            raise StopAsyncIteration
