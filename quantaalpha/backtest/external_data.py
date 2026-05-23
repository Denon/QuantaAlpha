"""
Shared external data loader for factor computation pipelines.
Loads CSV/Parquet files with date+instrument keys and returns a MultiIndex DataFrame.
"""

import logging
from pathlib import Path
from typing import Dict, Optional, List

import pandas as pd

logger = logging.getLogger(__name__)


def get_column_descriptions(config: Optional[Dict]) -> Dict[str, str]:
    """Extract column name → description mapping from external_data config.

    Reads the optional ``columns`` mapping per file entry in
    ``config['external_data']['files'][i]['columns']``.

    Args:
        config: Full config dict.

    Returns:
        Dict mapping column names to descriptions, or empty dict if none
        configured.
    """
    if not config:
        return {}

    ext_config = config.get("external_data")
    if not ext_config:
        return {}

    files: List[Dict] = ext_config.get("files", [])
    if not files:
        return {}

    result: Dict[str, str] = {}
    for entry in files:
        columns = entry.get("columns", {})
        if not columns:
            continue
        for col, desc in columns.items():
            if col in result:
                if result[col] != desc:
                    logger.warning(
                        f"Column '{col}' has conflicting descriptions: "
                        f"'{result[col]}' vs '{desc}'. Keeping first."
                    )
            else:
                result[col] = desc

    return result


def load_external_data(config: Optional[Dict]) -> Optional[pd.DataFrame]:
    """Load external factor data from configured CSV/Parquet files.

    Args:
        config: Full config dict. Reads from ``config['external_data']['files']``.

    Returns:
        DataFrame with MultiIndex (datetime, instrument) and factor columns,
        or None if no external data is configured.
    """
    if not config:
        return None

    ext_config = config.get("external_data")
    if not ext_config:
        return None

    files: List[Dict] = ext_config.get("files", [])
    if not files:
        logger.info("external_data section exists but 'files' is empty")
        return None

    all_dfs: List[pd.DataFrame] = []
    for entry in files:
        path = entry.get("path")
        fmt = entry.get("format", "csv")
        date_col = entry.get("date_column", "date")
        inst_col = entry.get("instrument_column", "instrument")

        if not path:
            logger.warning("Skipping external_data entry with no path")
            continue

        resolved = Path(path).expanduser()
        if not resolved.exists():
            logger.error(f"External data file not found, skipping: {resolved}")
            continue

        try:
            if fmt == "parquet":
                df = _load_parquet(resolved, date_col, inst_col)
            else:
                df = _load_csv(resolved, date_col, inst_col)
        except Exception as e:
            logger.error(f"Failed to load external data file {resolved}: {e}")
            continue

        if df.empty:
            logger.warning(f"External data file is empty, skipping: {resolved}")
            continue

        all_dfs.append(df)

    if not all_dfs:
        return None

    # Concatenate all file DataFrames (they share MultiIndex structure)
    result = pd.concat(all_dfs, axis=1)
    # Deduplicate columns — keep first occurrence
    dupe_mask = result.columns.duplicated(keep="first")
    if dupe_mask.any():
        dupe_names = result.columns[dupe_mask].tolist()
        logger.warning(f"Dropping duplicate external columns: {dupe_names}")
        result = result.loc[:, ~dupe_mask]

    return result


def _load_csv(path: Path, date_col: str, inst_col: str) -> pd.DataFrame:
    """Load a CSV file and return with MultiIndex (datetime, instrument)."""
    df = pd.read_csv(path, dtype={inst_col: str})
    _validate_columns(df, path, date_col, inst_col)
    date_col_raw = _try_parse_dates(df, date_col)
    df[date_col_raw] = pd.to_datetime(df[date_col_raw])
    df = df.set_index([date_col_raw, inst_col])
    df.index.names = ["datetime", "instrument"]
    df = df.sort_index()
    return df


def _load_parquet(path: Path, date_col: str, inst_col: str) -> pd.DataFrame:
    """Load a Parquet file and return with MultiIndex (datetime, instrument)."""
    df = pd.read_parquet(path)
    _validate_columns(df, path, date_col, inst_col)
    date_col_raw = _try_parse_dates(df, date_col)
    if not pd.api.types.is_datetime64_any_dtype(df[date_col_raw].dtype):
        df[date_col_raw] = pd.to_datetime(df[date_col_raw])
    df = df.set_index([date_col_raw, inst_col])
    df.index.names = ["datetime", "instrument"]
    df = df.sort_index()
    return df


def _validate_columns(df: pd.DataFrame, path: Path, date_col: str, inst_col: str):
    """Check required columns exist."""
    missing = [c for c in [date_col, inst_col] if c not in df.columns]
    if missing:
        raise ValueError(
            f"External data file {path} is missing required columns: {missing}. "
            f"Available columns: {list(df.columns)}"
        )


def _try_parse_dates(df: pd.DataFrame, date_col: str) -> str:
    """Return the actual date column name, handling common aliases.

    If the configured ``date_col`` is not found, try 'date' as fallback
    so that users can write ``date_column: date`` reliably.
    """
    if date_col in df.columns:
        return date_col
    # Fallback for common date column variations
    fallbacks = ["date", "Date", "DATE", "datetime", "DateTime", "trade_date"]
    for fb in fallbacks:
        if fb in df.columns:
            logger.debug(f"date_column '{date_col}' not found, using fallback '{fb}'")
            return fb
    return date_col
