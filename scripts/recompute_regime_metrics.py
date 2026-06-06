#!/usr/bin/env python3
"""Recompute regime metrics for factors lacking CSI300 data by re-evaluating
their expressions on CSI300 stock data via CustomFactorCalculator.

Usage:
    python scripts/recompute_regime_metrics.py [--dry-run]
"""

import argparse
import json
import logging
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def load_regime_map(path: str | None = None) -> pd.DataFrame:
    from scripts.build_regime_map import load_regime_map as _load
    return _load(path)


def compute_regime_metrics(
    factor_series: pd.Series,
    label_series: pd.Series,
    date_regime_map: dict,
    regime_labels: list,
    regime_months: dict,
) -> dict | None:
    """Compute per-regime metrics from a factor series and label series."""
    from quantaalpha.backtest.ic_metrics import compute_daily_ic

    if factor_series.empty:
        return None

    if not isinstance(factor_series.index, pd.MultiIndex):
        return None

    if list(factor_series.index.names) == ["instrument", "datetime"]:
        factor_series = factor_series.swaplevel().sort_index()

    label = label_series
    if (isinstance(label.index, pd.MultiIndex)
            and list(label.index.names) == ["instrument", "datetime"]):
        label = label.swaplevel().sort_index()

    daily_pearson, daily_rank, n_days, n_obs = compute_daily_ic(factor_series, label)
    if daily_pearson.empty:
        return None

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


def compute_regime_summary(regime_metrics: dict) -> dict:
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
    parser = argparse.ArgumentParser(description="Recompute regime metrics for factors on CSI300")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    library_path = project_root / "data/factorlib/all_factors_library.json"
    if not library_path.exists():
        logger.error(f"Factor library not found: {library_path}")
        sys.exit(1)

    logger.info(f"Loading factor library: {library_path}")
    with open(library_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    factors = data.get("factors", {})
    if not factors:
        logger.info("No factors found")
        return

    # Count factors needing recompute
    need_recompute = [
        (fid, finfo) for fid, finfo in factors.items()
        if isinstance(finfo, dict)
        and not finfo.get("regime_metrics")
        and finfo.get("factor_expression")
    ]
    logger.info(f"Factors needing regime metrics: {len(need_recompute)} / {len(factors)}")

    if not need_recompute:
        logger.info("All factors already have regime metrics")
        return

    # Initialize Qlib and load CSI300 data
    logger.info("Loading CSI300 data...")
    import qlib
    from qlib.data import D

    provider_uri = os.environ.get("QLIB_PROVIDER_URI", os.path.expanduser("~/.qlib/qlib_data/cn_data"))
    region = os.environ.get("QLIB_REGION", "cn")
    qlib.init(provider_uri=provider_uri, region=region)

    # Load regime map
    regime_map = load_regime_map()
    logger.info(f"Regime map: {len(regime_map)} months")

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
        ms, me = row["month_start"], row["month_end"]
        if isinstance(ms, pd.Timestamp) and isinstance(me, pd.Timestamp):
            for d in pd.date_range(ms, me, freq="B"):
                date_regime_map[d.date()] = regime
            if regime not in regime_months:
                regime_months[regime] = set()
            regime_months[regime].add((ms.year, ms.month))

    # Load labels for CSI300
    full_start = str(regime_map_copy["month_start"].min().date())
    full_end = str(regime_map_copy["month_end"].max().date())

    label_df = D.features(
        D.instruments("csi300"),
        ["Ref($close, -2)/Ref($close, -1) - 1"],
        start_time=full_start,
        end_time=full_end,
    )
    label_series = label_df.iloc[:, 0]
    logger.info(f"Label data: {label_series.shape}")

    # Load CSI300 stock data for expression evaluation
    logger.info("Loading CSI300 stock data for CustomFactorCalculator...")
    stock_fields = ["$open", "$high", "$low", "$close", "$volume", "$vwap"]
    stock_df = D.features(
        D.instruments("csi300"),
        stock_fields,
        start_time=full_start,
        end_time=full_end,
    )
    logger.info(f"Stock data: {stock_df.shape}")

    # Ensure (datetime, instrument) index
    if list(stock_df.index.names) == ["instrument", "datetime"]:
        stock_df = stock_df.swaplevel().sort_index()

    from quantaalpha.backtest.custom_factor_calculator import CustomFactorCalculator
    calc = CustomFactorCalculator(data_df=stock_df.copy())

    # Process each factor
    updated = 0
    failed = 0

    for fid, finfo in need_recompute:
        factor_name = finfo.get("factor_name", fid)
        factor_expr = finfo.get("factor_expression", "")
        logger.info(f"Evaluating: {factor_name}")

        try:
            factor_series = calc.calculate_factor(factor_name, factor_expr)

            if factor_series is None or factor_series.empty:
                logger.warning(f"  → Expression evaluation returned empty for {factor_name}")
                failed += 1
                continue

            metrics = compute_regime_metrics(
                factor_series, label_series,
                date_regime_map, regime_labels, regime_months,
            )

            if metrics:
                summary = compute_regime_summary(metrics)
                finfo["regime_metrics"] = metrics
                finfo["regime_summary"] = summary
                updated += 1
                logger.info(f"  → Updated: best={summary['best_regime']}, stability={summary['regime_stability']}")
            else:
                logger.warning(f"  → Could not compute regime metrics for {factor_name}")
                failed += 1

        except Exception as e:
            logger.warning(f"  → Failed for {factor_name}: {e}")
            failed += 1

    logger.info(f"Recompute complete: updated={updated}, failed={failed}")

    if not args.dry_run and updated > 0:
        data["metadata"]["last_updated"] = pd.Timestamp.now().isoformat()
        data["metadata"]["total_factors"] = len(factors)

        import shutil
        backup_path = library_path.with_suffix(".json.bak2")
        shutil.copy2(library_path, backup_path)
        logger.info(f"Backup: {backup_path}")

        with open(library_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2, default=str)
        logger.info(f"Written {updated} factors to {library_path}")
    elif args.dry_run:
        logger.info(f"[DRY RUN] Would update {updated} factors")


if __name__ == "__main__":
    main()
