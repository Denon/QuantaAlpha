#!/usr/bin/env python3
"""Monthly regime detection and validation.

Detects regime for every month in the data range, producing a richer
dataset for regime-stability analysis than per-fold (6-month) labeling.
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

# ── Init ───────────────────────────────────────────────────────────
qlib.init(provider_uri="~/.qlib/qlib_data/cn_data", region="cn")

# Fetch benchmark: CSI 300 from 2016 to 2025
bm_df = D.features(["SH000300"], ["$close"], start_time="2016-01-01", end_time="2025-12-31")
bm_prices = bm_df["$close"].droplevel("instrument")
print(f"Benchmark: {len(bm_prices)} days ({bm_prices.index[0].date()} → {bm_prices.index[-1].date()})")

# ── Detect once, aggregate monthly ─────────────────────────────────
detector = MarketRegimeDetector(VolatilityDirectionStrategy())

# One call for the full series
full_regime_series = detector.detect(prices=bm_prices, vol_window=60, n_regimes=2)
print(f"Per-date regime series: {len(full_regime_series)} entries")
print(f"Valid (non-None) labels: {full_regime_series.notna().sum()}")

# Aggregate to monthly dominant regime
monthly_regimes = []
for year in range(2016, 2026):
    for month in range(1, 13):
        month_start = pd.Timestamp(f"{year}-{month:02d}-01")
        if month == 12:
            month_end = pd.Timestamp(f"{year}-12-31")
        else:
            month_end = pd.Timestamp(f"{year}-{month+1:02d}-01") - pd.Timedelta(days=1)

        # Restrict to dates within this month
        mask = (full_regime_series.index >= month_start) & (full_regime_series.index <= month_end)
        month_series = full_regime_series[mask].dropna()

        if len(month_series) == 0:
            regime = None
        else:
            counts = month_series.value_counts()
            max_count = counts.max()
            top = counts[counts == max_count].index.tolist()
            if len(top) == 1:
                regime = top[0]
            else:
                # Tie-break: first chronological
                for label in month_series:
                    if label in top:
                        regime = label
                        break
                else:
                    regime = None

        monthly_regimes.append(
            {
                "year": year,
                "month": month,
                "month_start": month_start.date(),
                "month_end": month_end.date(),
                "regime": regime,
            }
        )

df = pd.DataFrame(monthly_regimes)
# Drop months with no regime (None)
df_valid = df.dropna(subset=["regime"])
print(f"Months with regime: {len(df_valid)} / {len(df)}")

# ── Distribution ───────────────────────────────────────────────────
print(f"\n{'='*70}")
print("Monthly Regime Distribution (2016-2025)")
print(f"{'='*70}")

dist = df_valid["regime"].value_counts()
for regime, count in dist.items():
    pct = count / len(df_valid) * 100
    bar = "█" * int(pct / 2)
    print(f"  {regime:<20} {count:>3} months ({pct:5.1f}%) {bar}")

# ── Year-by-year breakdown ────────────────────────────────────────
print(f"\n{'='*70}")
print("Year-by-Year Regime Breakdown")
print(f"{'='*70}")

print(f"{'Year':<6}", end="")
for m in range(1, 13):
    print(f"{m:>4}", end="")
print(f"  {'calm_bull':>10} {'calm_bear':>10} {'volatile_bull':>10} {'volatile_bear':>10}")
print("-" * 70)

for year in range(2016, 2026):
    print(f"{year:<6}", end="")
    year_data = df_valid[df_valid["year"] == year]
    counts = {"calm_bull": 0, "calm_bear": 0, "volatile_bull": 0, "volatile_bear": 0}
    for m in range(1, 13):
        month_data = year_data[year_data["month"] == m]
        if len(month_data) > 0:
            r = month_data.iloc[0]["regime"]
            # Abbreviate: cb=calm_bull, CB=calm_bear, vb=volatile_bull, VB=volatile_bear
            abbrev = {"calm_bull": "cb", "calm_bear": "CB", "volatile_bull": "vb", "volatile_bear": "VB"}
            print(f" {abbrev.get(r, '??'):>3}", end="")
            counts[r] = counts.get(r, 0) + 1
        else:
            print(f" {'--':>3}", end="")
    print(f"  {counts['calm_bull']:>10} {counts['calm_bear']:>10} {counts['volatile_bull']:>10} {counts['volatile_bear']:>10}")

# ── Regime persistence ─────────────────────────────────────────────
print(f"\n{'='*70}")
print("Regime Persistence (month-to-month transition probability)")
print(f"{'='*70}")

transitions = {}
prev = None
for _, row in df_valid.iterrows():
    curr = row["regime"]
    if prev is not None:
        key = (prev, curr)
        transitions[key] = transitions.get(key, 0) + 1
    prev = curr

regimes_list = sorted(dist.index.tolist())
header = "From \\ To"
print(f"{header:<16}", end="")
for r in regimes_list:
    print(f"{r:>16}", end="")
print()
for r_from in regimes_list:
    print(f"{r_from:<16}", end="")
    total_from = sum(transitions.get((r_from, r_to), 0) for r_to in regimes_list)
    for r_to in regimes_list:
        count = transitions.get((r_from, r_to), 0)
        pct = count / total_from * 100 if total_from > 0 else 0
        print(f"{count:>4} ({pct:5.1f}%)", end="")
    print()

# ── Average regime duration ────────────────────────────────────────
print(f"\n{'='*70}")
print("Average Regime Duration (consecutive months)")
print(f"{'='*70}")

for regime in regimes_list:
    durations = []
    current_run = 0
    for _, row in df_valid.iterrows():
        if row["regime"] == regime:
            current_run += 1
        else:
            if current_run > 0:
                durations.append(current_run)
                current_run = 0
    if current_run > 0:
        durations.append(current_run)
    if durations:
        print(f"  {regime:<20} mean={np.mean(durations):.1f}m  median={np.median(durations):.0f}m  max={max(durations)}m  runs={len(durations)}")
