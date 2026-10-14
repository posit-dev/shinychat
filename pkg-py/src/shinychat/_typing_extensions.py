# # Within file flags to ignore unused imports
# flake8: noqa: F401
# pyright: reportUnusedImport=false

__all__ = (
    "Annotated",
    "Concatenate",
    "ParamSpec",
    "TypeGuard",
    "TypeIs",
    "Never",
    "Required",
    "NotRequired",
    "Self",
    "TypedDict",
    "assert_type",
)


import sys

if sys.version_info >= (3, 9):
    from typing import Annotated
else:
    from typing_extensions import Annotated

if sys.version_info >= (3, 10):
    from typing import Concatenate, ParamSpec, TypeGuard
else:
    from typing_extensions import Concatenate, ParamSpec, TypeGuard

# TypedDict always comes from typing_extensions: pydantic requires
# `typing_extensions.TypedDict` (not `typing.TypedDict`) on Python < 3.12 for
# models with TypedDict-typed fields, and it interoperates with
# `typing.NotRequired` on 3.11+ (https://peps.python.org/pep-0655/).
from typing_extensions import TypedDict

if sys.version_info >= (3, 11):
    from typing import (
        Never,
        NotRequired,
        Required,
        Self,
        assert_type,
    )
else:
    from typing_extensions import (
        Never,
        NotRequired,
        Required,
        Self,
        assert_type,
    )

if sys.version_info >= (3, 13):
    from typing import TypeIs
else:
    from typing_extensions import TypeIs

# The only purpose of the following line is so that pyright will put all of the
# conditional imports into the .pyi file when generating type stubs. Without this line,
# pyright will not include the above imports in the generated .pyi file, and it will
# result in a lot of red squiggles in user code.
_: 'Annotated |Concatenate[str, ParamSpec("P")] | ParamSpec | TypeGuard | TypeIs | NotRequired | Required | TypedDict | assert_type | Self'  # type:ignore
