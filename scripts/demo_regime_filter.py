#!/usr/bin/env python3
"""Demo: regime-filtered factor query workflow.

Shows how the monthly regime map enables queries like:
  "What was the Rank IC of factor X during volatile_bear months between 2018-2020?"

Usage:
  python scripts/demo_regime_filter.py
  python scripts/demo_regime_filter.py --regime volatile_bear --start 2018-01-01 --end 2020-12-31
"""
import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))

import qlib
from qlib.data import D
from quantaalpha.backtest.ic_metrics import compute_factor_metrics
from scripts.build_regime_map import load_regime_map, filter_dates_by_regime


def main():
    parser = argparse.ArgumentParser(description="Regime-filtered factor query")
    parser.add_argument("--regime", type=str, default="volatile_bear",
                        help="Target regime")
    parser.add_argument("--start", type=str, default="2018-01-01")
    parser.add_argument("--end", type=str, default="2020-12-31")
    parser.add_argument("--stocks", type=int, default=30,
                        help="Number of stocks for cross-sectional IC")
    args = parser.parse_args()

    qlib.init(provider_uri="~/.qlib/qlib_data/cn_data", region="cn")

    # ── Step 1: Load regime map ──────────────────────────────────
    regime_map = load_regime_map()

    # ── Step 2: Filter months by regime + date range ─────────────
    if args.regime:
        target_months = filter_dates_by_regime(regime_map, args.regime, args.start, args.end)
    else:
        target_months = regime_map.copy()
        target_months = target_months[
            (target_months["month_start"] >= pd.Timestamp(args.start)) &
            (target_months["month_end"] <= pd.Timestamp(args.end))
        ]

    print(f"\n{'='*60}")
    print(f"Query: regime='{args.regime or 'all'}', {args.start}→{args.end}")
    print(f"{'='*60}")
    print(f"Matched {len(target_months)} months:")
    for _, row in target_months.iterrows():
        print(f"  {row['month_start']} → {row['month_end']}  [{row['regime']}]")
    print()

    # ── Step 3: Get stock universe ───────────────────────────────
    # Use known CSI 300 component stocks for cross-sectional IC
    stocks = ["SH600000", "SH600036", "SH600519", "SH601318", "SH600276",
              "SZ000001", "SZ000002", "SZ000858", "SZ002415", "SZ300750",
              "SH601166", "SH600030", "SH600887", "SH601012", "SH603288",
              "SZ000333", "SZ000651", "SZ002304", "SZ300059", "SZ300124",
              "SH600900", "SH601088", "SH600585", "SH601899", "SH603993",
              "SZ000568", "SZ000725", "SZ002142", "SZ300015", "SZ300498"][:args.stocks]
    label_expr = "Ref($close, -2) / Ref($close, -1) - 1"

    # ── Step 4: Compute IC for a simple momentum factor ──────────
    factor_expr = "$close"  # Raw close → cross-sectional rank IC

    print(f"Computing cross-sectional Rank IC for {factor_expr}")
    print(f"Across {args.stocks} stocks, {len(target_months)} months\n")

    raw_factor = D.features(stocks, [factor_expr], start_time=args.start, end_time=args.end)
    raw_label = D.features(stocks, [label_expr], start_time=args.start, end_time=args.end)

    f_series = raw_factor[factor_expr]
    l_series = raw_label[label_expr]
    if "instrument" in f_series.index.names:
        f_series = f_series.swaplevel("instrument", "datetime")
    if "instrument" in l_series.index.names:
        l_series = l_series.swaplevel("instrument", "datetime")

    # ── Step 5: For each target month, compute IC ────────────────
    ic_values = []
    for _, mrow in target_months.iterrows():
        ms = pd.Timestamp(mrow["month_start"])
        me = pd.Timestamp(mrow["month_end"])

        f_mask = (f_series.index.get_level_values("datetime") >= ms) & \
                 (f_series.index.get_level_values("datetime") <= me)
        l_mask = (l_series.index.get_level_values("datetime") >= ms) & \
                 (l_series.index.get_level_values("datetime") <= me)

        f_m = f_series[f_mask]
        l_m = l_series[l_mask]
        common = f_m.index.intersection(l_m.index)

        if len(common) < 30:
            continue

        try:
            m = compute_factor_metrics(f_m.loc[common], l_m.loc[common])
            ic_values.append(m["factor_metrics"]["Rank_IC"])
        except Exception:
            continue

    print(f"  Valid months with IC: {len(ic_values)}/{len(target_months)}")
    print(f"  Mean Rank IC: {np.mean(ic_values):+.4f}")
    print(f"  Median Rank IC: {np.median(ic_values):+.4f}")
    print(f"  Std Rank IC: {np.std(ic_values):.4f}")
    print(f"  Positive IC rate: {sum(1 for x in ic_values if x>0)/len(ic_values)*100:.0f}%")
    print(f"  t-statistic: {np.mean(ic_values)/(np.std(ic_values)/np.sqrt(len(ic_values))):.2f}")

    # ── Step 6: Compare with other regimes (if no specific filter) ─
    if not args.regime:
        return

    print(f"\n{'─'*60}")
    print("Comparison: same factor, different regimes")
    print(f"{'─'*60}")

    for other_regime in ["calm_bull", "volatile_bull", "calm_bear", "volatile_bear"]:
        other_months = filter_dates_by_regime(regime_map, other_regime, args.start, args.end)
        if len(other_months) == 0:
            continue

        other_ics = []
        for _, mrow in other_months.iterrows():
            ms, me = pd.Timestamp(mrow["month_start"]), pd.Timestamp(mrow["month_end"])
            f_mask = (f_series.index.get_level_values("datetime") >= ms) & \
                     (f_series.index.get_level_values("datetime") <= me)
            l_mask = (l_series.index.get_level_values("datetime") >= ms) & \
                     (l_series.index.get_level_values("datetime") <= me)
            f_m, l_m = f_series[f_mask], l_series[l_mask]
            common = f_m.index.intersection(l_m.index)
            if len(common) < 30:
                continue
            try:
                m = compute_factor_metrics(f_m.loc[common], l_m.loc[common])
                other_ics.append(m["factor_metrics"]["Rank_IC"])
            except Exception:
                continue

        if other_ics:
            marker = " ← CURRENT" if other_regime == args.regime else ""
            print(f"  {other_regime:<20} n={len(other_ics):>2}  "
                  f"Mean IC={np.mean(other_ics):+.4f}  "
                  f"Hit={(sum(1 for x in other_ics if x>0)/len(other_ics)*100):.0f}%{marker}")


if __name__ == "__main__":
    main()
