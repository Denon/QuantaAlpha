"""Market regime detection with pluggable strategy interface.

Provides a Protocol-based strategy pattern for classifying market conditions
(volatility + direction) and a facade for fold-level majority-vote labeling.
"""

from __future__ import annotations

import logging
from typing import Protocol

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class RegimeStrategy(Protocol):
    """Protocol for pluggable regime detection strategies.

    Any object implementing ``detect(prices, vol_window, n_regimes) -> pd.Series``
    satisfies this protocol (duck typing — no inheritance required).
    """

    def detect(
        self, prices: pd.Series, vol_window: int, n_regimes: int
    ) -> pd.Series:
        """Return regime labels indexed by datetime.

        Parameters
        ----------
        prices : pd.Series
            Price series with a DatetimeIndex (or datetime level).
        vol_window : int
            Rolling window size in trading days for volatility computation.
        n_regimes : int
            Number of volatility percentile buckets (≥2).

        Returns
        -------
        pd.Series
            Regime label strings indexed by the same datetime index.
            Dates where volatility cannot be computed have ``None`` labels.
        """
        ...


class VolatilityDirectionStrategy:
    """Two-dimensional regime classification: volatility percentile × direction.

    Regime labels are formatted as ``{vol_label}_{direction}``, e.g.
    ``"calm_bull"``, ``"calm_bear"``, ``"volatile_bull"``, ``"volatile_bear"``.

    The *volatility* dimension buckets the rolling standard deviation of daily
    returns into ``n_regimes`` percentile bins (default 2 → ``"calm"`` / ``"volatile"``).

    The *direction* dimension uses the sign of the cumulative return over the
    same window: positive → ``"bull"``, negative → ``"bear"``.

    Labels are broadcast forward: the regime detected for the last valid date
    in the window is assigned to *all* dates in that window.
    """

    VOL_LABELS = {2: ["calm", "volatile"], 3: ["calm", "normal", "volatile"]}

    def detect(
        self, prices: pd.Series, vol_window: int, n_regimes: int
    ) -> pd.Series:
        """Detect regime for each date in the price series.

        Parameters
        ----------
        prices : pd.Series
            Daily price series. Must have a DatetimeIndex-like index.
        vol_window : int
            Rolling window in trading days for volatility and return.
        n_regimes : int
            Number of volatility percentile buckets (2 or 3 supported).

        Returns
        -------
        pd.Series
            Regime label per date. Dates before ``vol_window`` data points
            are accumulated have label ``None``.
        """
        if not isinstance(prices, pd.Series):
            raise TypeError(f"prices must be a pd.Series, got {type(prices)}")

        if len(prices) < vol_window:
            logger.warning(
                "Price series has %d points < vol_window=%d; all regimes will be None.",
                len(prices),
                vol_window,
            )
            result = pd.Series([None] * len(prices), index=prices.index)
            result.name = "regime"
            return result

        returns = prices.pct_change(fill_method=None)
        rolling_vol = returns.rolling(window=vol_window, min_periods=vol_window).std()
        rolling_ret = prices.pct_change(periods=vol_window, fill_method=None)

        vol_labels = self.VOL_LABELS.get(n_regimes)
        if vol_labels is None:
            # Generic labels for arbitrary n_regimes
            vol_labels = [f"v{i}" for i in range(n_regimes)]

        regime_series = pd.Series([None] * len(prices), index=prices.index)

        # Compute percentile cutoffs from the full series of valid rolling vol
        valid_vol = rolling_vol.dropna()
        if len(valid_vol) == 0:
            result = pd.Series([None] * len(prices), index=prices.index)
            result.name = "regime"
            return result

        cutoffs = np.percentile(valid_vol, np.linspace(0, 100, n_regimes + 1)[1:-1])

        for i in range(len(prices)):
            vol_val = rolling_vol.iloc[i]
            ret_val = rolling_ret.iloc[i]
            if pd.isna(vol_val) or pd.isna(ret_val):
                regime_series.iloc[i] = None
                continue

            # Bucket volatility
            bucket = 0
            for j, cutoff in enumerate(cutoffs):
                if vol_val > cutoff:
                    bucket = j + 1
            vol_label = vol_labels[min(bucket, n_regimes - 1)]

            # Direction
            direction = "bull" if ret_val >= 0 else "bear"

            regime_series.iloc[i] = f"{vol_label}_{direction}"

        regime_series.name = "regime"
        return regime_series


class MarketRegimeDetector:
    """Facade for regime detection with majority-vote window labeling.

    Parameters
    ----------
    strategy : RegimeStrategy
        Any object implementing ``detect(prices, vol_window, n_regimes)``.
    """

    def __init__(self, strategy: RegimeStrategy) -> None:
        self.strategy = strategy

    def detect(
        self, prices: pd.Series, vol_window: int, n_regimes: int
    ) -> pd.Series:
        """Return per-date regime labels from the configured strategy.

        Parameters
        ----------
        prices : pd.Series
            Price series with DatetimeIndex.
        vol_window : int
            Rolling volatility window size.
        n_regimes : int
            Number of volatility buckets.

        Returns
        -------
        pd.Series
            Regime label per date (``None`` where insufficient data).
        """
        return self.strategy.detect(prices, vol_window, n_regimes)

    def dominant_regime(
        self,
        prices: pd.Series,
        vol_window: int,
        n_regimes: int,
        start: str | None = None,
        end: str | None = None,
    ) -> str | None:
        """Return the majority-vote regime within a date window.

        Prices are pre-sliced to the requested window before detection
        so that volatility percentiles and rolling statistics are computed
        from the window's own data — no lookahead or outside-window context.

        Parameters
        ----------
        prices : pd.Series
            Price series with DatetimeIndex.
        vol_window : int
            Rolling volatility window size.
        n_regimes : int
            Number of volatility buckets.
        start : str or None
            Start date (inclusive). If None, uses earliest date.
        end : str or None
            End date (inclusive). If None, uses latest date.

        Returns
        -------
        str or None
            Dominant regime label, or ``None`` if no valid labels exist.
            Ties are broken by chronological first appearance.
        """
        # Pre-slice prices so detect() uses only this window's data
        if start is not None:
            prices = prices[prices.index >= pd.Timestamp(start)]
        if end is not None:
            prices = prices[prices.index <= pd.Timestamp(end)]

        regime_series = self.detect(prices, vol_window, n_regimes)

        valid = regime_series.dropna()
        if len(valid) == 0:
            return None

        counts = valid.value_counts()
        max_count = counts.max()
        top_regimes = counts[counts == max_count].index.tolist()

        if len(top_regimes) == 1:
            return top_regimes[0]

        # Tie-break: first chronological appearance
        for label in valid:
            if label in top_regimes:
                return label

        return None
