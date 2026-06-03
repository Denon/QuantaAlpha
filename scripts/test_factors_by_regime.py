#!/usr/bin/env python3
"""Test specific factors across different regimes using the monthly regime map.

Picks RET_VOL5 (unstable) and MA_RATIO5_10 (stable) and compares their
Rank IC across all 4 regimes over 2010-2025.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))

import qlib
from qlib.data import D
from quantaalpha.backtest.ic_metrics import compute_factor_metrics
from scripts.build_regime_map import load_regime_map


def compute_monthly_ic_for_factors(
    factor_list: list[str],
    regime_map: pd.DataFrame,
    stock_count: int = 50,
) -> pd.DataFrame:
    """Compute monthly Rank IC for a list of alpha158 factor names.

    Uses Qlib Alpha158 handler to get precomputed factor values.
    """
    # Alpha158 handler for full date range
    from qlib.contrib.data.handler import Alpha158

    full_start = str(regime_map["month_start"].min())
    full_end = str(regime_map["month_end"].max())

    handler_conf = {
        "start_time": full_start,
        "end_time": full_end,
        "instruments": "csi300",
        "fit_start_time": full_start,
        "fit_end_time": full_end,
        "infer_processors": [],
        "learn_processors": [],
        "label": ["Ref($close, -2) / Ref($close, -1) - 1"],
    }

    print(f"Loading Alpha158 data ({full_start} → {full_end})...")
    handler = Alpha158(**handler_conf)
    features_df = handler.fetch(col_set="feature")
    label_df = handler.fetch(col_set="label")
    print(f"Features: {features_df.shape}, Labels: {label_df.shape}")

    # Map our factor names to Alpha158 column names
    # Alpha158 columns have prefixes; find matching columns
    col_map = {}
    for target in factor_list:
        matches = [c for c in features_df.columns if target.upper() in c.upper()]
        if matches:
            col_map[target] = matches[0]
            print(f"  {target} → {matches[0]}")
        else:
            print(f"  {target} → NOT FOUND (skipping)")

    # Normalize index
    if "instrument" in features_df.index.names:
        features_df = features_df.swaplevel("instrument", "datetime")
    if "instrument" in label_df.index.names:
        label_df = label_df.swaplevel("instrument", "datetime")

    label_series = label_df.iloc[:, 0]

    # Compute IC per month
    results = []
    for _, mrow in regime_map.iterrows():
        ms = pd.Timestamp(mrow["month_start"])
        me = pd.Timestamp(mrow["month_end"])
        regime = mrow["regime"]

        f_dates = features_df.index.get_level_values("datetime")
        l_dates = label_series.index.get_level_values("datetime")
        f_mask = (f_dates >= ms) & (f_dates <= me)
        l_mask = (l_dates >= ms) & (l_dates <= me)

        f_month = features_df[f_mask]
        l_month = label_series[l_mask]

        for target, col in col_map.items():
            if col not in f_month.columns:
                continue
            f_col = f_month[col]
            common_idx = f_col.index.intersection(l_month.index)
            if len(common_idx) < 30:
                continue

            try:
                metrics = compute_factor_metrics(
                    f_col.loc[common_idx], l_month.loc[common_idx]
                )
                fm = metrics["factor_metrics"]
                results.append({
                    "month_start": ms.date(),
                    "regime": regime,
                    "factor": target,
                    "Rank_IC": fm["Rank_IC"],
                    "Rank_ICIR": fm["Rank_ICIR"],
                    "IC": fm["IC"],
                    "n_days": fm["n_days"],
                    "n_obs": fm["n_obs"],
                })
            except Exception:
                continue

    return pd.DataFrame(results)


def main():
    qlib.init(provider_uri="~/.qlib/qlib_data/cn_data", region="cn")

    regime_map = load_regime_map()
    print(f"Regime map: {len(regime_map)} months\n")

    factors = ["ROC5", "ROC20", "RSV5"]
    df = compute_monthly_ic_for_factors(factors, regime_map)
    print(f"\nValid IC observations: {len(df)}\n")

    # ── Per-factor, per-regime summary ─────────────────────────
    regimes = ["calm_bull", "volatile_bull", "calm_bear", "volatile_bear"]

    print("=" * 80)
    print("Factor Performance by Regime (2010–2025, monthly IC)")
    print("=" * 80)

    for factor in factors:
        print(f"\n─── {factor} ───")
        print(f"{'Regime':<20} {'Months':>7} {'Mean Rank IC':>13} {'Std':>8} {'Hit Rate':>8} {'t-stat':>7}")
        print("-" * 65)
        for regime in regimes:
            subset = df[(df["factor"] == factor) & (df["regime"] == regime)]
            if len(subset) < 2:
                continue
            mean_ic = subset["Rank_IC"].mean()
            std_ic = subset["Rank_IC"].std()
            hit = (subset["Rank_IC"] > 0).mean() * 100
            t = mean_ic / (std_ic / np.sqrt(len(subset))) if std_ic > 0 else 0
            bar = "█" * int(abs(mean_ic) * 500)
            print(f"{regime:<20} {len(subset):>7} {mean_ic:>+13.4f} {std_ic:>8.4f} {hit:>7.0f}% {t:>+7.2f}  {bar}")

    # ── ANOVA test for each factor ─────────────────────────────
    from scipy.stats import f_oneway
    print(f"\n{'='*80}")
    print("ANOVA: Does regime significantly affect factor IC?")
    print(f"{'='*80}")
    for factor in factors:
        groups = [
            df[(df["factor"] == factor) & (df["regime"] == r)]["Rank_IC"].dropna()
            for r in regimes
            if len(df[(df["factor"] == factor) & (df["regime"] == r)]) > 1
        ]
        if len(groups) >= 2:
            f_stat, p_val = f_oneway(*groups)
            sig = "✓ SIGNIFICANT" if p_val < 0.05 else "✗ not significant"
            print(f"  {factor:<20} F={f_stat:.4f}  p={p_val:.4f}  {sig}")

    # ── Best regime for each factor ────────────────────────────
    print(f"\n{'='*80}")
    print("Best Regime per Factor (by Mean Rank IC)")
    print(f"{'='*80}")
    for factor in factors:
        best = None
        best_mean = -999
        for regime in regimes:
            subset = df[(df["factor"] == factor) & (df["regime"] == regime)]
            if len(subset) < 2:
                continue
            m = subset["Rank_IC"].mean()
            if m > best_mean:
                best_mean = m
                best = regime
        print(f"  {factor:<20} → {best} (Mean IC = {best_mean:+.4f})")


if __name__ == "__main__":
    main()
