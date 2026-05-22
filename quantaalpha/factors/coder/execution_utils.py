from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any


def ensure_return_column(df: Any) -> Any:
    if "$return" in df.columns:
        return df
    if "$close" not in df.columns:
        return df

    group_level = "instrument" if "instrument" in getattr(df.index, "names", []) else 0
    df["$return"] = df.groupby(level=group_level)["$close"].pct_change().fillna(0)
    return df


def replace_dataframe_symbols(expr: str, columns: Iterable[str]) -> str:
    for col in sorted(columns, key=len, reverse=True):
        symbol = col[1:] if col.startswith("$") else col
        replacement = f"df[{col!r}]"
        expr = re.sub(
            rf"(?<![A-Za-z0-9_]){re.escape(symbol)}(?![A-Za-z0-9_])",
            replacement,
            expr,
        )
    return expr

