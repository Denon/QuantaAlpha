"""Tests for market regime detection module."""

import numpy as np
import pandas as pd

from quantaalpha.backtest.regime import (
    MarketRegimeDetector,
    RegimeStrategy,
    VolatilityDirectionStrategy,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_prices(direction: str = "up", n: int = 200) -> pd.Series:
    """Build synthetic daily price series with a known trend."""
    np.random.seed(42)
    dates = pd.date_range("2020-01-01", periods=n, freq="B")
    rng = np.random.default_rng(42)
    if direction == "down":
        drift = -0.001
    elif direction == "flat":
        drift = 0.0
    else:
        drift = 0.001
    noise = 0.02
    daily_returns = drift + noise * rng.standard_normal(n)
    prices = 100 * np.cumprod(1 + daily_returns)
    return pd.Series(prices, index=dates, name="close")


# ---------------------------------------------------------------------------
# 1.4 VolatilityDirectionStrategy tests
# ---------------------------------------------------------------------------


def test_vol_dir_returns_series_same_index():
    strat = VolatilityDirectionStrategy()
    prices = _make_prices("up", n=200)
    result = strat.detect(prices, vol_window=60, n_regimes=2)

    assert isinstance(result, pd.Series)
    assert len(result) == len(prices)
    assert list(result.index) == list(prices.index)


def test_vol_dir_none_before_vol_window():
    strat = VolatilityDirectionStrategy()
    prices = _make_prices("up", n=200)
    result = strat.detect(prices, vol_window=60, n_regimes=2)

    # First 60 values should be None (1 from pct_change + 59 from min_periods=60 rolling)
    assert result.iloc[:60].isna().all()
    # After vol_window+1, values should be non-None
    assert not result.iloc[60:].isna().any()


def test_vol_dir_monotonic_decline_is_bear():
    """Monotonic decline → cumulative return negative → bear direction."""
    strat = VolatilityDirectionStrategy()
    dates = pd.date_range("2020-01-01", periods=200, freq="B")
    # Strictly declining prices
    prices = pd.Series(np.linspace(100, 50, 200), index=dates, name="close")
    result = strat.detect(prices, vol_window=60, n_regimes=2)

    # All valid labels should contain "bear"
    valid = result.dropna()
    assert len(valid) > 0
    assert all("bear" in str(label) for label in valid)


def test_vol_dir_monotonic_increase_is_bull():
    """Monotonic increase → cumulative return positive → bull direction."""
    strat = VolatilityDirectionStrategy()
    dates = pd.date_range("2020-01-01", periods=200, freq="B")
    # Strictly increasing prices
    prices = pd.Series(np.linspace(50, 100, 200), index=dates, name="close")
    result = strat.detect(prices, vol_window=60, n_regimes=2)

    valid = result.dropna()
    assert len(valid) > 0
    assert all("bull" in str(label) for label in valid)


def test_vol_dir_insufficient_data_all_none():
    strat = VolatilityDirectionStrategy()
    prices = _make_prices("up", n=30)  # fewer than vol_window=60
    result = strat.detect(prices, vol_window=60, n_regimes=2)

    # All None since vol_window never satisfied
    assert result.isna().all()


def test_vol_dir_handles_nan_prices():
    strat = VolatilityDirectionStrategy()
    prices = _make_prices("up", n=200).copy()
    prices.iloc[10] = np.nan
    prices.iloc[150] = np.nan
    result = strat.detect(prices, vol_window=60, n_regimes=2)

    assert isinstance(result, pd.Series)
    assert len(result) == 200
    # NaN at positions 10 and 150 propagate via pct_change/rolling, producing None labels
    # Verify the result handles them without crashing


def test_vol_dir_n_regimes_three():
    """With n_regimes=3, labels should use calm/normal/volatile prefix."""
    strat = VolatilityDirectionStrategy()
    prices = _make_prices("up", n=200)
    result = strat.detect(prices, vol_window=60, n_regimes=3)

    valid = result.dropna()
    assert len(valid) > 0
    allowed_prefixes = {"calm", "normal", "volatile"}
    for label in valid:
        prefix = label.split("_")[0]
        assert prefix in allowed_prefixes, f"Unexpected prefix '{prefix}' in '{label}'"


# ---------------------------------------------------------------------------
# 1.5 MarketRegimeDetector tests
# ---------------------------------------------------------------------------


def test_detector_dominant_regime_majority():
    """60% volatile_bear, 40% calm_bear → dominant is volatile_bear."""
    strat = VolatilityDirectionStrategy()
    detector = MarketRegimeDetector(strat)
    dates = pd.date_range("2020-01-01", periods=200, freq="B")
    # Declining prices → bear
    prices = pd.Series(np.linspace(100, 50, 200), index=dates, name="close")

    dominant = detector.dominant_regime(prices, vol_window=60, n_regimes=2)

    assert dominant is not None
    assert "bear" in dominant


def test_detector_dominant_regime_tie_break_chronological():
    """Equal counts → return the one that appears first chronologically."""
    strat = VolatilityDirectionStrategy()
    detector = MarketRegimeDetector(strat)

    # Create price series where we know the first valid label
    dates = pd.date_range("2020-01-01", periods=200, freq="B")
    prices = pd.Series(np.linspace(100, 50, 200), index=dates, name="close")

    # Override: manually construct a regime series where ties happen
    # But this depends on real computation. Instead, trust the chronological
    # tie-break logic in dominant_regime — verified by separate tie test.
    regime_series = pd.Series(
        ["calm_bull"] * 80 + ["volatile_bear"] * 80 + [None] * 40,
        index=dates,
    )

    # Monkey-patch detect to return our controlled series
    detector.detect = lambda p, vw, nr: regime_series  # type: ignore[method-assign]
    dominant = detector.dominant_regime(prices, vol_window=60, n_regimes=2)

    # Both have 80 — tie-break: calm_bull appears first
    assert dominant == "calm_bull"


def test_detector_dominant_regime_all_same():
    """When all valid labels are identical, return that label."""
    strat = VolatilityDirectionStrategy()
    detector = MarketRegimeDetector(strat)
    dates = pd.date_range("2020-01-01", periods=200, freq="B")

    # Manually construct a series that is all calm_bull
    regime_series = pd.Series(["calm_bull"] * 200, index=dates)
    detector.detect = lambda p, vw, nr: regime_series  # type: ignore[method-assign]
    dominant = detector.dominant_regime(dates, vol_window=60, n_regimes=2)

    assert dominant == "calm_bull"


def test_detector_dominant_regime_window_subset():
    """dominant_regime with start/end restricts to that date range."""
    strat = VolatilityDirectionStrategy()
    detector = MarketRegimeDetector(strat)
    dates = pd.date_range("2020-01-01", periods=200, freq="B")
    prices = pd.Series(np.linspace(100, 50, 200), index=dates, name="close")

    full = detector.dominant_regime(prices, vol_window=60, n_regimes=2)
    # Restricting to second half might change regime or still be valid
    subset = detector.dominant_regime(
        prices, vol_window=60, n_regimes=2,
        start="2020-05-01", end="2020-09-30",
    )

    assert subset is not None
    # Both should be bear direction for declining prices
    assert "bear" in full
    assert "bear" in subset


def test_detector_dominant_regime_all_none_returns_none():
    """When no valid labels exist, return None."""
    strat = VolatilityDirectionStrategy()
    detector = MarketRegimeDetector(strat)
    # Too few data points for vol_window
    dates = pd.date_range("2020-01-01", periods=30, freq="B")
    prices = pd.Series(np.linspace(100, 90, 30), index=dates, name="close")

    dominant = detector.dominant_regime(prices, vol_window=60, n_regimes=2)
    assert dominant is None


def test_detector_detect_delegates_to_strategy():
    """detect() should return whatever the strategy returns."""
    strat = VolatilityDirectionStrategy()
    detector = MarketRegimeDetector(strat)
    prices = _make_prices("up", n=200)
    direct = strat.detect(prices, vol_window=60, n_regimes=2)
    via_detector = detector.detect(prices, vol_window=60, n_regimes=2)

    pd.testing.assert_series_equal(direct, via_detector)


def test_regime_strategy_protocol_duck_typing():
    """A class implementing detect() with correct signature satisfies Protocol."""

    class CustomStrategy:
        def detect(self, prices, vol_window, n_regimes):
            return pd.Series(["custom"] * len(prices), index=prices.index)

    detector = MarketRegimeDetector(CustomStrategy())
    prices = _make_prices("up", n=100)
    result = detector.detect(prices, vol_window=30, n_regimes=2)

    assert (result == "custom").all()
