"""
Per-factor IC metrics computation.

Computes daily cross-sectional Pearson IC and Spearman Rank IC between
a factor series and the aligned forward-return label, then aggregates
to per-factor summary statistics.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field, asdict
from typing import Iterable, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class FactorICMetrics:
    """Aggregated per-factor IC metrics stored in factor_metrics."""

    IC: float = 0.0
    IC_std: float = 0.0
    ICIR: float = 0.0
    Rank_IC: float = 0.0
    Rank_IC_std: float = 0.0
    Rank_ICIR: float = 0.0
    n_days: int = 0
    n_obs: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class MetricContext:
    """Computation context stored alongside factor_metrics for staleness detection."""

    provider_uri: str = ""
    market: str = ""
    start_time: str = ""
    end_time: str = ""
    label_expr: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def compute_daily_ic(
    factor_series: pd.Series,
    label_series: pd.Series,
    min_instruments: int = 3,
) -> tuple[pd.Series, pd.Series, int, int]:
    """Compute daily cross-sectional Pearson IC and Spearman Rank IC.

    Args:
        factor_series: Factor values with MultiIndex (datetime, instrument).
        label_series: Forward-return label with MultiIndex (datetime, instrument).
        min_instruments: Minimum number of instruments required per day.

    Returns:
        (daily_pearson_ic, daily_rank_ic, n_days_valid, n_obs_total)
        where daily_* are pd.Series indexed by datetime with valid daily IC values.
    """
    _ensure_multiindex(factor_series, "factor")
    _ensure_multiindex(label_series, "label")

    common_idx = factor_series.index.intersection(label_series.index)
    if len(common_idx) == 0:
        logger.warning("Factor and label have no overlapping (datetime, instrument) pairs")
        return pd.Series(dtype=float), pd.Series(dtype=float), 0, 0

    factor_aligned = factor_series.reindex(common_idx)
    label_aligned = label_series.reindex(common_idx)

    factor_grp = factor_aligned.groupby(level="datetime")
    label_grp = label_aligned.groupby(level="datetime")

    pearson_list: list[tuple[pd.Timestamp, float]] = []
    rank_list: list[tuple[pd.Timestamp, float]] = []
    n_obs_total = 0

    for dt, _ in factor_aligned.groupby(level="datetime"):
        f_group = factor_grp.get_group(dt)
        l_group = label_grp.get_group(dt)

        # Align factor and label: keep only rows where both have non-NaN values
        paired = pd.concat([f_group, l_group], axis=1, join="inner").dropna()
        f_clean = paired.iloc[:, 0].values
        l_clean = paired.iloc[:, 1].values

        if len(f_clean) < min_instruments:
            continue

        n_obs_total += len(f_clean)

        # Pearson IC
        corr_mat = np.corrcoef(f_clean, l_clean)
        if not np.isnan(corr_mat[0, 1]):
            pearson_list.append((dt, corr_mat[0, 1]))

        # Spearman Rank IC
        f_rank = _rank_vector(f_clean)
        l_rank = _rank_vector(l_clean)
        rank_corr = np.corrcoef(f_rank, l_rank)
        if not np.isnan(rank_corr[0, 1]):
            rank_list.append((dt, rank_corr[0, 1]))

    daily_pearson = pd.Series(
        dict(pearson_list), name="pearson_ic"
    )
    daily_rank = pd.Series(dict(rank_list), name="rank_ic")

    return daily_pearson, daily_rank, len(pearson_list), n_obs_total


def aggregate_ic_metrics(
    daily_pearson: pd.Series,
    daily_rank: pd.Series,
) -> FactorICMetrics:
    """Aggregate daily IC series into FactorICMetrics.

    Args:
        daily_pearson: Daily Pearson IC values (pd.Series).
        daily_rank: Daily Spearman Rank IC values (pd.Series).

    Returns:
        FactorICMetrics with aggregate statistics.
    """
    metrics = FactorICMetrics()

    if len(daily_pearson) > 0:
        ic_mean = float(daily_pearson.mean())
        ic_std = float(daily_pearson.std(ddof=1))  # sample std
        metrics.IC = ic_mean
        metrics.IC_std = ic_std if not np.isnan(ic_std) else 0.0
        metrics.ICIR = ic_mean / ic_std if ic_std > 1e-12 else 0.0
        metrics.n_days = len(daily_pearson)

    if len(daily_rank) > 0:
        ric_mean = float(daily_rank.mean())
        ric_std = float(daily_rank.std(ddof=1))
        metrics.Rank_IC = ric_mean
        metrics.Rank_IC_std = ric_std if not np.isnan(ric_std) else 0.0
        metrics.Rank_ICIR = ric_mean / ric_std if ric_std > 1e-12 else 0.0

    # n_obs is set by the caller (compute_factor_metrics) from compute_daily_ic output

    return metrics


def classify_quality(metrics: Optional[FactorICMetrics], n_days_threshold: int = 10) -> str:
    """Classify factor quality from FactorICMetrics.

    Classification is based exclusively on Rank IC:
      - high:   abs(Rank_IC) >= 0.03 and n_days >= n_days_threshold
      - medium: abs(Rank_IC) >= 0.01 and n_days >= n_days_threshold
      - low:    valid metrics with abs(Rank_IC) < 0.01 and n_days >= n_days_threshold
      - unknown: no metrics, all null values, or n_days < n_days_threshold

    Args:
        metrics: FactorICMetrics instance or None.
        n_days_threshold: Minimum number of valid days required.

    Returns:
        One of 'high', 'medium', 'low', 'unknown'.
    """
    if metrics is None:
        return "unknown"

    # Check that we have real data
    if metrics.n_days < n_days_threshold:
        return "unknown"
    if metrics.Rank_IC is None:
        return "unknown"
    if metrics.Rank_IC == 0.0 and metrics.Rank_IC_std == 0.0 and metrics.n_days == 0:
        return "unknown"

    abs_rank_ic = abs(metrics.Rank_IC)
    if abs_rank_ic >= 0.03:
        return "high"
    if abs_rank_ic >= 0.01:
        return "medium"
    return "low"


def compute_factor_metrics(
    factor_series: pd.Series,
    label_series: pd.Series,
    metric_context: Optional[MetricContext] = None,
) -> dict:
    """Compute factor_metrics dict for a single factor against a label.

    This is the main entry point used by both library enrichment and
    standalone backtest IC computation.

    Args:
        factor_series: Factor values with MultiIndex (datetime, instrument).
        label_series: Label values with MultiIndex (datetime, instrument).
        metric_context: Optional MetricContext to store alongside metrics.

    Returns:
        dict with 'factor_metrics' (aggregate IC stats) and optionally 'metric_context'.
    """
    daily_pearson, daily_rank, n_days, n_obs = compute_daily_ic(
        factor_series, label_series
    )
    metrics = aggregate_ic_metrics(daily_pearson, daily_rank)
    metrics.n_obs = n_obs

    result: dict = {"factor_metrics": metrics.to_dict()}
    if metric_context is not None:
        result["metric_context"] = metric_context.to_dict()
    return result


def _ensure_multiindex(series: pd.Series, name: str):
    """Validate series has a MultiIndex with datetime and instrument levels."""
    if not isinstance(series.index, pd.MultiIndex):
        raise ValueError(
            f"{name} series must have a MultiIndex, got {type(series.index)}"
        )
    names = list(series.index.names)
    if "datetime" not in names or "instrument" not in names:
        raise ValueError(
            f"{name} series index must have 'datetime' and 'instrument' levels, "
            f"got {names}"
        )


def _rank_vector(arr: np.ndarray) -> np.ndarray:
    """Compute rank of each element (1..N), handling ties via average."""
    if len(arr) == 0:
        return arr
    sorter = np.argsort(arr, kind="mergesort")
    rank = np.empty(len(arr), dtype=float)
    rank[sorter] = np.arange(1, len(arr) + 1, dtype=float)
    # Handle ties by averaging ranks
    unique_vals, inv, counts = np.unique(arr, return_inverse=True, return_counts=True)
    if len(counts) > 0 and counts.max() > 1:
        for val_idx, count in enumerate(counts):
            if count > 1:
                mask = inv == val_idx
                rank[mask] = rank[mask].mean()
    return rank
