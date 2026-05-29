"""Reusable precomputed dataset builder for Qlib DatasetH construction.

Extracted from BacktestRunner._create_dataset_with_computed_factors so both
static backtests and walk-forward folds can build datasets from pre-aligned
feature/label DataFrames."""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def _normalize_multiindex(df: pd.DataFrame, df_name: str) -> pd.DataFrame:
    """Ensure MultiIndex has standard (datetime, instrument) level names."""
    if not isinstance(df.index, pd.MultiIndex):
        logger.warning(f"  {df_name} index is not MultiIndex: {type(df.index)}")
        return df

    names = list(df.index.names)
    new_names = list(names)
    for i, name in enumerate(names):
        level_vals = df.index.get_level_values(i)
        if name == "datetime" or name == "date":
            new_names[i] = "datetime"
        elif name == "instrument" or name == "stock":
            new_names[i] = "instrument"
        elif name is None:
            if pd.api.types.is_datetime64_any_dtype(level_vals):
                new_names[i] = "datetime"
            elif level_vals.dtype == object or pd.api.types.is_string_dtype(level_vals):
                new_names[i] = "instrument"

    if new_names != names:
        logger.debug(f"  {df_name} index renamed: {names} -> {new_names}")
        df.index = df.index.set_names(new_names)

    actual_names = list(df.index.names)
    if len(actual_names) == 2 and actual_names == ["instrument", "datetime"]:
        df = df.swaplevel()
        df = df.sort_index()
        logger.debug(f"  {df_name} index swapped to (datetime, instrument)")

    return df


def _align_features_and_labels(
    features_df: pd.DataFrame, label_df: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Align features and label DataFrames on their (datetime, instrument) index."""
    common_index = features_df.index.intersection(label_df.index)

    if len(common_index) == 0 and len(features_df) > 0 and len(label_df) > 0:
        logger.warning("  Index intersection empty, aligning datetime types...")
        feat_dt = features_df.index.get_level_values("datetime")
        label_dt = label_df.index.get_level_values("datetime")

        try:
            if not pd.api.types.is_datetime64_any_dtype(feat_dt):
                features_df.index = features_df.index.set_levels(
                    pd.to_datetime(feat_dt.unique()), level="datetime"
                )
            if not pd.api.types.is_datetime64_any_dtype(label_dt):
                label_df.index = label_df.index.set_levels(
                    pd.to_datetime(label_dt.unique()), level="datetime"
                )
        except Exception as e:
            logger.warning(f"  datetime type conversion failed: {e}")

        common_index = features_df.index.intersection(label_df.index)

    if len(common_index) == 0:
        feat_reset = features_df.reset_index()
        label_reset = label_df.reset_index()
        dt_col = "datetime" if "datetime" in feat_reset.columns else feat_reset.columns[0]
        inst_col = "instrument" if "instrument" in feat_reset.columns else feat_reset.columns[1]

        merged = pd.merge(feat_reset, label_reset, on=[dt_col, inst_col], how="inner")
        if len(merged) == 0:
            raise ValueError(
                f"Factor and label data could not be aligned. "
                f"features: {len(features_df)} rows, index names={list(features_df.index.names)}; "
                f"label: {len(label_df)} rows, index names={list(label_df.index.names)}"
            )

        merged = merged.set_index([dt_col, inst_col])
        merged.index.names = ["datetime", "instrument"]

        feature_cols = [c for c in features_df.columns if c in merged.columns]
        label_cols = [c for c in label_df.columns if c in merged.columns]
        features_df = merged[feature_cols]
        label_df = merged[label_cols]
    else:
        features_df = features_df.loc[common_index]
        label_df = label_df.loc[common_index]

    return features_df, label_df


def build_precomputed_dataset(
    features_df: pd.DataFrame,
    label_df: pd.DataFrame,
    segments: dict,
) -> "DatasetH":
    """Build a Qlib DatasetH from precomputed feature and label DataFrames.

    Handles index normalization, NaN/inf filling, cross-sectional rank
    normalization, and PrecomputedDataHandler construction.

    Args:
        features_df: Feature values with (datetime, instrument) or
                     (instrument, datetime) MultiIndex.
        label_df: Label values with matching index structure.
        segments: Qlib segments dict mapping 'train'/'valid'/'test' to
                  [start_date, end_date] pairs.

    Returns:
        A Qlib DatasetH ready for model training and prediction.
    """
    from qlib.data.dataset import DatasetH
    from qlib.data.dataset.handler import DataHandler

    features_df = _normalize_multiindex(features_df, "features")
    label_df = _normalize_multiindex(label_df, "label")

    features_df, label_df = _align_features_and_labels(features_df, label_df)

    logger.debug(f"  Data rows: {len(features_df)}")
    if len(features_df) == 0:
        raise ValueError("No rows after index alignment; cannot run backtest")

    combined_df = pd.concat([features_df, label_df], axis=1)
    feature_cols = list(features_df.columns)
    label_cols = list(label_df.columns)

    combined_df[feature_cols] = combined_df[feature_cols].fillna(0)
    combined_df[feature_cols] = combined_df[feature_cols].replace([np.inf, -np.inf], 0)

    dt_level = combined_df.index.names[0] if combined_df.index.names[0] else 0
    for col in feature_cols:
        combined_df[col] = combined_df.groupby(level=dt_level)[col].transform(
            lambda x: (x.rank(pct=True) - 0.5) if len(x) > 1 else 0
        )

    combined_df = combined_df.dropna(subset=label_cols)
    for col in label_cols:
        combined_df[col] = combined_df.groupby(level=dt_level)[col].transform(
            lambda x: (x.rank(pct=True) - 0.5) if len(x) > 1 else 0
        )

    combined_df_multi = combined_df.copy()
    combined_df_multi.columns = pd.MultiIndex.from_tuples(
        [("feature", col) for col in feature_cols] + [("label", col) for col in label_cols]
    )

    class PrecomputedDataHandler(DataHandler):
        """DataHandler backed by a precomputed MultiIndex DataFrame."""

        def __init__(self, data_df, segments):
            self._data = data_df
            self._segments = segments

        @property
        def data_loader(self):
            return None

        @property
        def instruments(self):
            try:
                return list(self._data.index.get_level_values("instrument").unique())
            except KeyError:
                return list(self._data.index.get_level_values(1).unique())

        def fetch(self, selector=None, level="datetime", col_set="feature",
                  data_key=None, squeeze=False, proc_func=None):
            if col_set in ("feature", "label"):
                result = self._data[col_set].copy()
            elif col_set == "__all" or col_set is None:
                result = self._data.copy()
            else:
                if isinstance(col_set, (list, tuple)):
                    result = self._data[list(col_set)].copy()
                else:
                    result = self._data.copy()

            if selector is not None:
                try:
                    dates = result.index.get_level_values("datetime")
                except KeyError:
                    dates = result.index.get_level_values(0)
                if isinstance(selector, tuple) and len(selector) == 2:
                    start, end = selector
                    mask = (dates >= pd.Timestamp(start)) & (dates <= pd.Timestamp(end))
                    result = result.loc[mask]
                elif isinstance(selector, slice):
                    start = selector.start
                    end = selector.stop
                    if start is not None and end is not None:
                        mask = (dates >= pd.Timestamp(start)) & (dates <= pd.Timestamp(end))
                        result = result.loc[mask]

            if squeeze and result.shape[1] == 1:
                result = result.iloc[:, 0]
            return result

        def get_cols(self, col_set="feature"):
            if col_set in self._data.columns.get_level_values(0):
                return list(self._data[col_set].columns)
            return list(self._data.columns.get_level_values(1))

        def setup_data(self, **kwargs):
            pass

        def config(self, **kwargs):
            pass

    handler = PrecomputedDataHandler(combined_df_multi, segments)
    return DatasetH(handler=handler, segments=segments)
