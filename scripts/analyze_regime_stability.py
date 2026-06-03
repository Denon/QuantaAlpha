#!/usr/bin/env python3
"""Compare factor performance across same-regime folds.

Analyzes whether factors that performed well in one volatile_bear period
also rank highly in another volatile_bear period — testing the core
hypothesis behind regime-aware factor selection.
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))

import qlib
from qlib.data import D

from quantaalpha.backtest.runner import BacktestRunner
from quantaalpha.backtest.walk_forward import load_walk_forward_config, generate_walk_forward_folds
from quantaalpha.backtest.precomputed_dataset import _normalize_multiindex

# ── Load config and init ──────────────────────────────────────────
config_path = project_root / "configs" / "regime_smoke_test.yaml"
runner = BacktestRunner(str(config_path))
wf_config = load_walk_forward_config(runner.config)
runner._init_qlib()

# ── Generate folds and filter to volatile_bear ─────────────────────
folds = generate_walk_forward_folds(wf_config)
print(f"Total folds: {len(folds)}")

# Prepare feature/label data
features_df = runner.prepare_feature_frame()
label_df = runner._compute_label(runner.config["dataset"]["label"])
label_df = _normalize_multiindex(label_df, "label")
label_series = label_df["LABEL0"]

print(f"Features: {list(features_df.columns)}")
print(f"Feature shape: {features_df.shape}")

# ── Score EVERY factor in EVERY fold's selection window ────────────
from quantaalpha.backtest.factor_selection import score_factor_window

all_scores: dict[int, dict[str, dict]] = {}

for fold in folds:
    fold_scores = {}
    for factor_name in features_df.columns:
        score = score_factor_window(
            factor_name=factor_name,
            factor_series=features_df[factor_name],
            label_series=label_series,
            selection_start=str(fold.selection_start.date()),
            selection_end=str(fold.selection_end.date()),
            min_days=10,
        )
        if score is not None:
            fold_scores[factor_name] = {
                "rank_ic": score.rank_ic,
                "rank_icir": score.rank_icir,
                "ic": score.ic,
                "icir": score.icir,
                "n_days": score.n_days,
            }
        else:
            fold_scores[factor_name] = None

    # Sort by abs(Rank_IC) for ranking
    ranked = sorted(
        [(n, s) for n, s in fold_scores.items() if s is not None],
        key=lambda x: -abs(x[1]["rank_ic"]),
    )
    all_scores[fold.fold_id] = {
        "scores": fold_scores,
        "ranked": ranked,
        "selection_start": str(fold.selection_start.date()),
        "selection_end": str(fold.selection_end.date()),
    }

# ── Detect regime for each fold ────────────────────────────────────
from quantaalpha.backtest.regime import MarketRegimeDetector, VolatilityDirectionStrategy

benchmark = runner.config.get("backtest", {}).get("backtest", {}).get("benchmark", "SH000300")
data_cfg = runner.config.get("data", {})
bm_df = D.features([benchmark], ["$close"], start_time=data_cfg["start_time"], end_time=data_cfg["end_time"])
bm_prices = bm_df["$close"].droplevel("instrument")

detector = MarketRegimeDetector(VolatilityDirectionStrategy())
fold_regimes = {}
for fold in folds:
    r = detector.dominant_regime(
        prices=bm_prices,
        vol_window=wf_config.regime_vol_window,
        n_regimes=wf_config.regime_n_regimes,
        start=str(fold.selection_start.date()),
        end=str(fold.selection_end.date()),
    )
    fold_regimes[fold.fold_id] = r

# ── Identify volatile_bear folds ───────────────────────────────────
vb_folds = {fid: reg for fid, reg in fold_regimes.items() if reg == "volatile_bear"}
print(f"\nVolatile_bear folds: {vb_folds}")
vb_fold_ids = sorted(vb_folds.keys())

if len(vb_fold_ids) < 2:
    print("Need at least 2 volatile_bear folds to compare. Exiting.")
    sys.exit(0)

# ── Cross-comparison ───────────────────────────────────────────────
fold_a = vb_fold_ids[0]
fold_b = vb_fold_ids[1]

print(f"\n{'='*80}")
print(f"Comparing volatile_bear folds:")
print(f"  Fold {fold_a}: {all_scores[fold_a]['selection_start']} → {all_scores[fold_a]['selection_end']}")
print(f"  Fold {fold_b}: {all_scores[fold_b]['selection_start']} → {all_scores[fold_b]['selection_end']}")
print(f"{'='*80}")

# Build comparison table
rank_a = {name: i + 1 for i, (name, _) in enumerate(all_scores[fold_a]["ranked"])}
rank_b = {name: i + 1 for i, (name, _) in enumerate(all_scores[fold_b]["ranked"])}
scores_a = all_scores[fold_a]["scores"]
scores_b = all_scores[fold_b]["scores"]

rows = []
for factor_name in features_df.columns:
    sa = scores_a.get(factor_name)
    sb = scores_b.get(factor_name)
    if sa is None or sb is None:
        continue
    rows.append(
        {
            "factor": factor_name,
            f"fold{fold_a}_rank_ic": round(sa["rank_ic"], 4),
            f"fold{fold_a}_rank_icir": round(sa["rank_icir"], 4),
            f"fold{fold_a}_rank": rank_a.get(factor_name, "-"),
            f"fold{fold_b}_rank_ic": round(sb["rank_ic"], 4),
            f"fold{fold_b}_rank_icir": round(sb["rank_icir"], 4),
            f"fold{fold_b}_rank": rank_b.get(factor_name, "-"),
        }
    )

df = pd.DataFrame(rows)
df["rank_change"] = df[f"fold{fold_a}_rank"] - df[f"fold{fold_b}_rank"]
df["abs_rank_change"] = df["rank_change"].abs()

# Sort by average rank
df["avg_rank"] = (df[f"fold{fold_a}_rank"] + df[f"fold{fold_b}_rank"]) / 2
df = df.sort_values("avg_rank")

print(f"\n{'─'*80}")
print("Full factor ranking comparison (sorted by average rank across both folds)")
print(f"{'─'*80}")
print(
    f"{'Factor':<20} {'IC_A':>8} {'ICIR_A':>8} {'Rank_A':>6} "
    f"{'IC_B':>8} {'ICIR_B':>8} {'Rank_B':>6} {'ΔRank':>6}"
)
print(f"{'─'*80}")

for _, row in df.iterrows():
    marker = " ★" if row["abs_rank_change"] <= 3 else ""
    print(
        f"{row['factor']:<20} "
        f"{row[f'fold{fold_a}_rank_ic']:>8.4f} "
        f"{row[f'fold{fold_a}_rank_icir']:>8.4f} "
        f"{row[f'fold{fold_a}_rank']:>6} "
        f"{row[f'fold{fold_b}_rank_ic']:>8.4f} "
        f"{row[f'fold{fold_b}_rank_icir']:>8.4f} "
        f"{row[f'fold{fold_b}_rank']:>6} "
        f"{int(row['rank_change']):>+6d}"
        f"{marker}"
    )

# ── Summary statistics ─────────────────────────────────────────────
print(f"\n{'='*80}")
print("Summary")
print(f"{'='*80}")

# Rank correlation
from scipy.stats import spearmanr, pearsonr

ranks_a = df[f"fold{fold_a}_rank"].values
ranks_b = df[f"fold{fold_b}_rank"].values
spearman_corr, spearman_p = spearmanr(ranks_a, ranks_b)
pearson_corr, pearson_p = pearsonr(
    df[f"fold{fold_a}_rank_ic"].values, df[f"fold{fold_b}_rank_ic"].values
)

print(f"\nSpearman rank correlation: {spearman_corr:.4f} (p={spearman_p:.4f})")
print(f"Pearson correlation (Rank_IC): {pearson_corr:.4f} (p={pearson_p:.4f})")

# Overlap in top-5
top5_a = set(df.head(5)["factor"].tolist())
top5_b = set(df.nsmallest(5, f"fold{fold_b}_rank")["factor"].tolist())
overlap = top5_a & top5_b
print(f"\nTop-5 overlap: {len(overlap)}/5 factors")
if overlap:
    for f in sorted(overlap):
        print(f"  ✓ {f} (rank {rank_a[f]}/{rank_b[f]})")

print(f"\nFactors with stable rank (|Δ| ≤ 3):")
stable = df[df["abs_rank_change"] <= 3]
for _, row in stable.iterrows():
    print(f"  {row['factor']:<20} rank {int(row[f'fold{fold_a}_rank']):>2} → {int(row[f'fold{fold_b}_rank']):>2}")

print(f"\nFactors with large rank shift (|Δ| ≥ 10):")
unstable = df[df["abs_rank_change"] >= 10]
if len(unstable) == 0:
    print("  (none — all factors relatively stable across same-regime folds)")
else:
    for _, row in unstable.iterrows():
        print(f"  {row['factor']:<20} rank {int(row[f'fold{fold_a}_rank']):>2} → {int(row[f'fold{fold_b}_rank']):>2}")

# Per-regime rank stability summary
print(f"\n{'='*80}")
print("Cross-Regime Rank Stability Comparison")
print(f"{'='*80}")

# Group folds by regime
regime_fold_groups: dict[str, list[int]] = {}
for fid, reg in fold_regimes.items():
    regime_fold_groups.setdefault(reg, []).append(fid)

for regime, fids in sorted(regime_fold_groups.items()):
    if len(fids) < 2:
        continue
    print(f"\n{regime} ({len(fids)} folds):")
    fid_a, fid_b = fids[0], fids[1]
    r_a = {name: i + 1 for i, (name, _) in enumerate(all_scores[fid_a]["ranked"])}
    r_b = {name: i + 1 for i, (name, _) in enumerate(all_scores[fid_b]["ranked"])}
    common = set(r_a) & set(r_b)
    ra = [r_a[n] for n in common]
    rb = [r_b[n] for n in common]
    corr, p = spearmanr(ra, rb)
    top5_a_set = set(sorted(common, key=lambda n: r_a[n])[:5])
    top5_b_set = set(sorted(common, key=lambda n: r_b[n])[:5])
    overlap_n = len(top5_a_set & top5_b_set)
    print(f"  Spearman ρ = {corr:.4f}  |  Top-5 overlap = {overlap_n}/5")
