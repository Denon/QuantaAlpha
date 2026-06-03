#!/usr/bin/env python3
"""Build and save a monthly regime classification map for the CSI 300 benchmark.

Produces: data/regime/monthly_regime_map.csv

Columns: year, month, month_start, month_end, regime, n_trading_days

Usage as a library:
    from scripts.build_regime_map import load_regime_map, filter_dates_by_regime
    rm = load_regime_map()
    volatile_bear_months = rm[rm["regime"] == "volatile_bear"]
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))

import qlib
from qlib.data import D
from quantaalpha.backtest.regime import MarketRegimeDetector, VolatilityDirectionStrategy


def build_regime_map(
    benchmark: str = "SH000300",
    start: str = "2010-01-01",
    end: str = "2025-12-31",
    vol_window: int = 60,
    n_regimes: int = 2,
) -> pd.DataFrame:
    """Build monthly regime classification map.

    Returns DataFrame with columns: year, month, month_start, month_end, regime, n_trading_days
    """
    qlib.init(provider_uri="~/.qlib/qlib_data/cn_data", region="cn")

    # Fetch benchmark prices
    bm_df = D.features([benchmark], ["$close"], start_time=start, end_time=end)
    bm_prices = bm_df["$close"].droplevel("instrument")

    # Detect regime once for all dates
    detector = MarketRegimeDetector(VolatilityDirectionStrategy())
    full_regime = detector.detect(prices=bm_prices, vol_window=vol_window, n_regimes=n_regimes)

    # Aggregate per month
    rows = []
    for year in range(pd.Timestamp(start).year, pd.Timestamp(end).year + 1):
        for month in range(1, 13):
            ms = pd.Timestamp(f"{year}-{month:02d}-01")
            if month == 12:
                me = pd.Timestamp(f"{year}-12-31")
            else:
                me = pd.Timestamp(f"{year}-{month+1:02d}-01") - pd.Timedelta(days=1)

            mask = (full_regime.index >= ms) & (full_regime.index <= me)
            month_series = full_regime[mask].dropna()
            n_days = len(month_series)

            if n_days == 0:
                regime = None
            else:
                counts = month_series.value_counts()
                max_count = counts.max()
                top = counts[counts == max_count].index.tolist()
                if len(top) == 1:
                    regime = top[0]
                else:
                    for label in month_series:
                        if label in top:
                            regime = label
                            break
                    else:
                        regime = None

            rows.append({
                "year": year,
                "month": month,
                "month_start": ms.date(),
                "month_end": me.date(),
                "regime": regime,
                "n_trading_days": n_days,
            })

    df = pd.DataFrame(rows)
    df.dropna(subset=["regime"], inplace=True)
    return df


def load_regime_map(path: str | None = None) -> pd.DataFrame:
    """Load the pre-built regime map."""
    if path is None:
        path = str(project_root / "data" / "regime" / "monthly_regime_map.csv")
    df = pd.read_csv(path, parse_dates=["month_start", "month_end"])
    return df


def filter_dates_by_regime(
    regime_map: pd.DataFrame,
    regime: str,
    start: str | None = None,
    end: str | None = None,
) -> pd.DataFrame:
    """Return months matching the given regime within an optional date range."""
    df = regime_map[regime_map["regime"] == regime].copy()
    if start:
        df = df[df["month_start"] >= pd.Timestamp(start)]
    if end:
        df = df[df["month_end"] <= pd.Timestamp(end)]
    return df.sort_values("month_start")


if __name__ == "__main__":
    # Build and save
    df = build_regime_map()
    output_dir = project_root / "data" / "regime"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "monthly_regime_map.csv"
    df.to_csv(output_path, index=False)
    print(f"Saved: {output_path}")
    print(f"Rows: {len(df)} months")
    print(f"Regimes: {df['regime'].value_counts().to_dict()}")
