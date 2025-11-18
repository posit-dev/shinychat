__all__ = ["MISSING", "MISSING_TYPE"]


class MISSING_TYPE:
    """Sentinel value for missing function parameters."""

    pass


MISSING: MISSING_TYPE = MISSING_TYPE()
