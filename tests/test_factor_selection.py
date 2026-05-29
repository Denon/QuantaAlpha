"""Tests for window-aware factor selection scoring."""

import numpy as np
import pandas as pd

from quantaalpha.backtest.factor_selection import select_top_factors, score_factor_window


def _series(name: str, values: list[float]) -> pd.Series:
    dates = pd.date_range("2024-01-01", periods=4, freq="D")
    instruments = ["A", "B", "C", "D"]
    idx = pd.MultiIndex.from_product([dates, instruments], names=["datetime", "instrument"])
    repeated = np.resize(np.array(values, dtype=float), len(idx))
    return pd.Series(repeated, index=idx, name=name)


def test_select_top_factors_uses_only_requested_window():
    label = _series("LABEL0", [1.0, 2.0, 3.0, 4.0])
    features = pd.DataFrame(
        {
            "strong": label + 0.001,
            "weak": _series("weak", [4.0, 1.0, 3.0, 2.0]),
            "empty": np.nan,
        }
    )

    result = select_top_factors(
        features_df=features,
        label_series=label,
        selection_start="2024-01-01",
        selection_end="2024-01-04",
        top_k=2,
        min_days=2,
    )

    assert [score.factor_name for score in result.selected] == ["strong", "weak"]
    assert "empty" in result.rejected


def test_score_factor_window_returns_none_for_insufficient_days():
    dates = pd.date_range("2024-01-01", periods=5, freq="D")
    instruments = ["A", "B"]
    idx = pd.MultiIndex.from_product([dates, instruments], names=["datetime", "instrument"])
    factor = pd.Series([1.0, 2.0] * 5, index=idx, name="short")
    label = pd.Series([0.01, -0.01] * 5, index=idx, name="LABEL0")

    score = score_factor_window("short", factor, label, "2024-01-01", "2024-01-05", min_days=10)

    assert score is None


def test_window_slicing_respects_date_boundaries():
    dates = pd.date_range("2024-01-01", periods=10, freq="D")
    instruments = ["A", "B", "C"]
    idx = pd.MultiIndex.from_product([dates, instruments], names=["datetime", "instrument"])
    np.random.seed(42)
    factor = pd.Series(np.random.randn(len(idx)), index=idx, name="f")
    label = pd.Series(np.random.randn(len(idx)), index=idx, name="LABEL0")

    # Only use first 3 days for selection
    result = select_top_factors(
        features_df=pd.DataFrame({"f": factor}),
        label_series=label,
        selection_start="2024-01-01",
        selection_end="2024-01-03",
        top_k=1,
        min_days=2,
    )

    assert len(result.selected) == 1
    score = result.selected[0]
    assert score.n_days <= 3
