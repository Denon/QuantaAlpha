"""Window-aware factor selection scoring.

Scores candidate factors within a specified date window using cross-sectional
IC/ICIR metrics and selects the top-k factors."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from quantaalpha.backtest.ic_metrics import compute_factor_metrics


@dataclass(frozen=True)
class FactorScore:
    factor_name: str
    rank_ic: float
    rank_icir: float
    ic: float
    icir: float
    n_days: int
    n_obs: int

    @property
    def sort_key(self) -> tuple:
        return (-abs(self.rank_ic), -abs(self.rank_icir), -self.n_days, self.factor_name)


@dataclass(frozen=True)
class FactorSelectionResult:
    selected: list[FactorScore]
    rejected: dict[str, str]
    all_scores: list[FactorScore]


def _window_slice(series: pd.Series, start: str, end: str) -> pd.Series:
    dates = series.index.get_level_values("datetime")
    mask = (dates >= pd.Timestamp(start)) & (dates <= pd.Timestamp(end))
    return series.loc[mask]


def score_factor_window(
    factor_name: str,
    factor_series: pd.Series,
    label_series: pd.Series,
    selection_start: str,
    selection_end: str,
    min_days: int,
) -> FactorScore | None:
    factor_window = _window_slice(factor_series, selection_start, selection_end)
    label_window = _window_slice(label_series, selection_start, selection_end)
    result = compute_factor_metrics(factor_window, label_window)
    metrics = result["factor_metrics"]
    if metrics["n_days"] < min_days:
        return None
    return FactorScore(
        factor_name=factor_name,
        rank_ic=float(metrics["Rank_IC"]),
        rank_icir=float(metrics["Rank_ICIR"]),
        ic=float(metrics["IC"]),
        icir=float(metrics["ICIR"]),
        n_days=int(metrics["n_days"]),
        n_obs=int(metrics["n_obs"]),
    )


def select_top_factors(
    features_df: pd.DataFrame,
    label_series: pd.Series,
    selection_start: str,
    selection_end: str,
    top_k: int,
    min_days: int = 10,
) -> FactorSelectionResult:
    scores: list[FactorScore] = []
    rejected: dict[str, str] = {}
    for factor_name in features_df.columns:
        score = score_factor_window(
            factor_name=factor_name,
            factor_series=features_df[factor_name],
            label_series=label_series,
            selection_start=selection_start,
            selection_end=selection_end,
            min_days=min_days,
        )
        if score is None:
            rejected[factor_name] = "insufficient_valid_days"
        else:
            scores.append(score)

    scores.sort(key=lambda score: score.sort_key)
    selected = scores if top_k == 0 else scores[:top_k]
    return FactorSelectionResult(selected=selected, rejected=rejected, all_scores=scores)
