from __future__ import annotations

from typing import Any


def groupby_level_or_column(obj: Any, name: str) -> Any:
    """Group by a named index level when present, otherwise by a column label."""
    index = getattr(obj, "index", None)
    index_names = list(getattr(index, "names", []) or [])
    index_name = getattr(index, "name", None)

    if name in index_names or index_name == name:
        return obj.groupby(level=name)
    return obj.groupby(name)


def groupby_instrument(obj: Any) -> Any:
    return groupby_level_or_column(obj, "instrument")


def groupby_datetime(obj: Any) -> Any:
    return groupby_level_or_column(obj, "datetime")

