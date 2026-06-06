#!/usr/bin/env python3
"""Backfill regime_metrics and regime_summary for existing factors in a factor library JSON.

Reads factor values from result.h5 cache files (same approach as build_regime_table()),
computes daily IC using Qlib labels, groups by regime, and writes regime_metrics and
regime_summary back to the JSON.

Usage:
    python scripts/backfill_regime_metrics.py [--library data/factorlib/all_factors_library.json]
"""

import argparse
import json
import logging
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# Ensure project root is in path
project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def load_regime_map(path: str | None = None) -> pd.DataFrame:
    """Load monthly regime map CSV."""
    from scripts.build_regime_map import load_regime_map as _load
    return _load(path)


def compute_regime_metrics_from_h5(
    h5_path: str,
    label_series: pd.Series,
    date_regime_map: dict,
    regime_labels: list,
    regime_months: dict,
) -> dict | None:
    """Compute per-regime metrics from a result.h5 file.

    Reads factor values from H5, computes daily IC against Qlib labels,
    and groups by regime. Uses the instruments present in the H5 file
    rather than filtering to a fixed universe.
    """
    from quantaalpha.backtest.ic_metrics import compute_daily_ic

    h5_file = Path(h5_path)
    if not h5_file.exists():
        logger.debug(f"H5 file not found: {h5_path}")
        return None

    try:
        df = pd.read_hdf(h5_path)
        if isinstance(df, pd.DataFrame):
            factor_series = df.iloc[:, 0] if df.shape[1] >= 1 else df
        elif isinstance(df, pd.Series):
            factor_series = df
        else:
            logger.debug(f"Unexpected H5 data type: {type(df)}")
            return None

        if factor_series.empty:
            return None

        # Ensure (datetime, instrument) index order
        if not isinstance(factor_series.index, pd.MultiIndex):
            logger.debug("Factor series is not MultiIndex; skipping")
            return None

        # Swap if needed: (instrument, datetime) -> (datetime, instrument)
        if list(factor_series.index.names) == ["instrument", "datetime"]:
            factor_series = factor_series.swaplevel().sort_index()

        # Swap label if needed
        if (isinstance(label_series.index, pd.MultiIndex)
                and list(label_series.index.names) == ["instrument", "datetime"]):
            label_series = label_series.swaplevel().sort_index()

        # Compute daily IC
        daily_pearson, daily_rank, n_days, n_obs = compute_daily_ic(factor_series, label_series)
        if daily_pearson.empty:
            logger.debug("No daily IC computed")
            return None

        # Group by regime
        regime_pearson = {}
        regime_rank = {}

        for dt in daily_pearson.index:
            dt_date = dt.date() if hasattr(dt, "date") else pd.Timestamp(dt).date()
            regime = date_regime_map.get(dt_date)
            if regime is None:
                continue
            if regime not in regime_pearson:
                regime_pearson[regime] = []
                regime_rank[regime] = []
            regime_pearson[regime].append(float(daily_pearson[dt]))
            if dt in daily_rank.index:
                regime_rank[regime].append(float(daily_rank[dt]))

        # Compute metrics per regime
        result = {}
        for regime in regime_labels:
            pearson_vals = regime_pearson.get(regime, [])
            rank_vals = regime_rank.get(regime, [])
            if not pearson_vals:
                continue
            n = len(pearson_vals)
            mean_ic = sum(pearson_vals) / n
            std_ic = (sum((v - mean_ic) ** 2 for v in pearson_vals) / (n - 1)) ** 0.5 if n > 1 else 0.0
            icir = mean_ic / std_ic if std_ic > 0 else 0.0

            mean_rank_ic = sum(rank_vals) / len(rank_vals) if rank_vals else 0.0
            std_rank_ic = (sum((v - mean_rank_ic) ** 2 for v in rank_vals) / (len(rank_vals) - 1)) ** 0.5 if len(rank_vals) > 1 else 0.0
            rank_icir = mean_rank_ic / std_rank_ic if std_rank_ic > 0 else 0.0

            hit_rate = sum(1 for v in pearson_vals if v > 0) / n if n > 0 else 0.0
            n_months = len(regime_months.get(regime, set()))

            result[regime] = {
                "IC": round(mean_ic, 6),
                "ICIR": round(icir, 4),
                "Rank_IC": round(mean_rank_ic, 6),
                "Rank_ICIR": round(rank_icir, 4),
                "hit_rate": round(hit_rate, 4),
                "n_days": n,
                "n_months": n_months,
            }

        return result if result else None

    except Exception as e:
        logger.debug(f"Failed to compute regime metrics from H5: {e}")
        return None


def compute_regime_summary(regime_metrics: dict) -> dict:
    """Compute regime_summary from per-regime metrics."""
    rank_ics = {r: abs(float(m.get("Rank_IC", 0))) for r, m in regime_metrics.items()}
    if not rank_ics:
        return {}
    best_regime = max(rank_ics, key=rank_ics.get)
    worst_regime = min(rank_ics, key=rank_ics.get)
    values = list(rank_ics.values())
    mean_abs = sum(values) / len(values)
    if mean_abs > 0 and len(values) > 1:
        variance = sum((v - mean_abs) ** 2 for v in values) / (len(values) - 1)
        std_dev = variance ** 0.5
        stability = max(0.0, min(1.0, 1.0 - std_dev / mean_abs))
    else:
        stability = 1.0
    return {
        "best_regime": best_regime,
        "worst_regime": worst_regime,
        "regime_stability": round(stability, 4),
    }


def main():
    parser = argparse.ArgumentParser(description="Backfill regime metrics for existing factors")
    parser.add_argument(
        "--library",
        default="data/factorlib/all_factors_library.json",
        help="Path to factor library JSON (relative to project root)",
    )
    parser.add_argument(
        "--regime-map",
        default=None,
        help="Path to regime map CSV (default: auto-load)",
    )
    parser.add_argument("--dry-run", action="store_true", help="Preview only, do not write")
    args = parser.parse_args()

    library_path = project_root / args.library
    if not library_path.exists():
        logger.error(f"Factor library not found: {library_path}")
        sys.exit(1)

    logger.info(f"Loading factor library: {library_path}")
    with open(library_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    factors = data.get("factors", {})
    if not factors:
        logger.info("No factors found in library")
        return

    logger.info("Loading regime map...")
    try:
        import qlib
        from qlib.data import D

        provider_uri = os.environ.get(
            "QLIB_PROVIDER_URI",
            os.path.expanduser("~/.qlib/qlib_data/cn_data"),
        )
        region = os.environ.get("QLIB_REGION", "cn")
        qlib.init(provider_uri=provider_uri, region=region)

        regime_map = load_regime_map(args.regime_map)
        logger.info(f"Loaded regime map with {len(regime_map)} months")

        # Build date-to-regime lookup and regime months tracking
        regime_map_copy = regime_map.copy()
        regime_map_copy["month_start"] = pd.to_datetime(regime_map_copy["month_start"])
        regime_map_copy["month_end"] = pd.to_datetime(regime_map_copy["month_end"])

        regime_labels = sorted(regime_map_copy["regime"].dropna().unique())
        date_regime_map = {}
        regime_months = {}

        for _, row in regime_map_copy.iterrows():
            regime = row["regime"]
            if pd.isna(regime):
                continue
            ms = row["month_start"]
            me = row["month_end"]
            if isinstance(ms, pd.Timestamp) and isinstance(me, pd.Timestamp):
                dates_in_month = pd.date_range(ms, me, freq="B")
                for d in dates_in_month:
                    date_regime_map[d.date()] = regime
                if regime not in regime_months:
                    regime_months[regime] = set()
                regime_months[regime].add((ms.year, ms.month))

        # Load label data for ALL instruments (full date range from regime map)
        full_start = str(regime_map_copy["month_start"].min().date())
        full_end = str(regime_map_copy["month_end"].max().date())

        label_expr = "Ref($close, -2)/Ref($close, -1) - 1"
        label_df = D.features(
            D.instruments("all"),
            [label_expr],
            start_time=full_start,
            end_time=full_end,
        )
        label_series = label_df.iloc[:, 0]

        if (isinstance(label_series.index, pd.MultiIndex)
                and list(label_series.index.names) == ["instrument", "datetime"]):
            label_series = label_series.swaplevel().sort_index()

        logger.info(f"Label data loaded: {label_series.shape}")

    except Exception as e:
        logger.error(f"Failed to initialize Qlib/regime map: {e}")
        sys.exit(1)

    total = len(factors)
    updated = 0
    skipped = 0
    failed = 0
    already_have = 0

    for fid, finfo in factors.items():
        if not isinstance(finfo, dict):
            skipped += 1
            continue

        factor_name = finfo.get("factor_name", fid)

        # Skip if already has regime data
        if finfo.get("regime_metrics") and finfo.get("regime_summary"):
            already_have += 1
            continue

        # Get H5 path from cache_location
        h5_path = finfo.get("cache_location", {}).get("result_h5_path", "")
        if not h5_path:
            logger.debug(f"Skipping {factor_name}: no result.h5 cache")
            skipped += 1
            continue

        logger.info(f"Computing regime metrics for: {factor_name} ({fid})")
        try:
            metrics = compute_regime_metrics_from_h5(
                h5_path,
                label_series,
                date_regime_map,
                regime_labels,
                regime_months,
            )
            if metrics:
                summary = compute_regime_summary(metrics)
                finfo["regime_metrics"] = metrics
                finfo["regime_summary"] = summary
                updated += 1
                logger.info(f"  → Updated: best={summary.get('best_regime', '?')}, "
                           f"stability={summary.get('regime_stability', '?')}")
            else:
                logger.debug(f"  → No regime metrics computed for {factor_name}")
                failed += 1
        except Exception as e:
            logger.warning(f"Failed for {factor_name}: {e}")
            failed += 1

    logger.info(
        f"Backfill complete: total={total}, updated={updated}, "
        f"skipped={skipped}, failed={failed}, already_have={already_have}"
    )

    if not args.dry_run and updated > 0:
        data["metadata"]["last_updated"] = pd.Timestamp.now().isoformat()
        data["metadata"]["total_factors"] = len(factors)
        # Backup before overwriting
        import shutil
        backup_path = library_path.with_suffix(".json.bak")
        shutil.copy2(library_path, backup_path)
        logger.info(f"Backup saved to {backup_path}")

        with open(library_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2, default=str)
        logger.info(f"Written {updated} updated factors to {library_path}")
    elif args.dry_run:
        logger.info(f"[DRY RUN] Would update {updated} factors")


if __name__ == "__main__":
    main()
