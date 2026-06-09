__all__ = ["DEPRECATED", "DEPRECATED_TYPE", "MISSING", "MISSING_TYPE"]


class MISSING_TYPE:
    """Sentinel value for missing function parameters."""

    pass


MISSING: MISSING_TYPE = MISSING_TYPE()


class DEPRECATED_TYPE:
    """Sentinel default for removed parameters that still accept calls for a helpful error."""

    pass


DEPRECATED: DEPRECATED_TYPE = DEPRECATED_TYPE()
