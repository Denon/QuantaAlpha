#!/usr/bin/env python3
"""
One-time backfill script: recompute per-factor IC metrics for existing factors
in the factor library that were saved before the per-factor IC feature was added.

For each factor, reads the cached result.h5, detects the actual date range and
instruments, computes labels for that exact scope, and computes per-factor IC.

Usage:
    python scripts/backfill_factor_metrics.py [--library data/factorlib/all_factors_library.json] [--config configs/backtest.yaml]

Requires:
    - Qlib data available (same provider_uri as in config)
    - Factor cache result.h5 files still present on disk
"""

import argparse
import json
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))


def init_qlib_from_config(config_path: str):
    """Initialize Qlib using data config."""
    import yaml
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    import os
    import qlib
    data_config = config["data"]
    provider_uri = os.path.expanduser(data_config["provider_uri"])
    qlib.init(provider_uri=provider_uri, region=data_config.get("region", "cn"))
    logger.info(f"Qlib initialized: {provider_uri}")
    return config


def compute_label_for_scope(instruments: list, start_time: str, end_time: str,
                            label_expr: str) -> pd.DataFrame:
    """Compute label for a specific instrument list and date range."""
    from qlib.data import D

    label_df = D.features(
        instruments,
        [label_expr],
        start_time=start_time,
        end_time=end_time,
        freq="day",
    )
    label_df.columns = ["LABEL0"]
    return label_df


def backfill_factor_metrics(
    library_path: str,
    config_path: str,
    dry_run: bool = False,
    force: bool = False,
    max_factors: int = 0,
):
    """Backfill per-factor IC metrics for factors missing them."""
    from quantaalpha.backtest.ic_metrics import (
        compute_factor_metrics,
        MetricContext,
        classify_quality,
        FactorICMetrics,
    )

    config = init_qlib_from_config(config_path)
    from qlib.data import D

    data_config = config["data"]
    dataset_config = config["dataset"]
    label_expr = dataset_config["label"]

    # Load library
    lib_path = Path(library_path)
    if not lib_path.exists():
        logger.error(f"Library not found: {lib_path}")
        return

    with open(lib_path, "r", encoding="utf-8") as f:
        library = json.load(f)

    factors = library.get("factors", {})
    total = len(factors)
    logger.info(f"Library: {total} factors")

    # Find factors needing backfill
    to_backfill = {}
    for fid, finfo in factors.items():
        has_metrics = bool(finfo.get("factor_metrics"))
        if force or not has_metrics:
            to_backfill[fid] = finfo

    if not to_backfill:
        logger.info("All factors already have factor_metrics. Use --force to recompute.")
        return

    logger.info(f"Factors to backfill: {len(to_backfill)}")

    updated = 0
    skipped_no_h5 = 0
    skipped_error = 0

    # Group factors by workspace to compute label once per experiment
    workspace_groups = {}
    for fid, finfo in to_backfill.items():
        ws_path = finfo.get("cache_location", {}).get("workspace_path", "")
        if ws_path:
            workspace_groups.setdefault(ws_path, []).append(fid)
        else:
            # Treat each factor as its own group
            workspace_groups.setdefault(fid, []).append(fid)

    for group_key, group_fids in workspace_groups.items():
        logger.info(f"\nWorkspace: {Path(group_key).name if group_key != group_fids[0] else '(standalone)'} "
                   f"({len(group_fids)} factors)")

        # Load the first factor's h5 to detect date range and instruments
        first_info = to_backfill[group_fids[0]]
        h5_path = first_info.get("cache_location", {}).get("result_h5_path", "")

        if not h5_path or not Path(h5_path).exists():
            ws = first_info.get("cache_location", {}).get("workspace_path", "")
            fd = first_info.get("cache_location", {}).get("factor_dir", "")
            alt_path = Path(ws) / fd / "result.h5" if ws and fd else None
            if alt_path and alt_path.exists():
                h5_path = str(alt_path)
            else:
                logger.warning(f"  Workspace h5 not found ({h5_path}), skipping all factors")
                for fid in group_fids:
                    skipped_no_h5 += 1
                continue

        try:
            sample_data = pd.read_hdf(h5_path)
        except Exception as e:
            logger.warning(f"  Failed to read {h5_path}: {e}")
            for fid in group_fids:
                skipped_error += 1
            continue

        if isinstance(sample_data, pd.DataFrame):
            sample_series = sample_data.iloc[:, 0]
        else:
            sample_series = sample_data

        if not isinstance(sample_series.index, pd.MultiIndex):
            logger.warning(f"  Invalid index (not MultiIndex), skipping workspace")
            for fid in group_fids:
                skipped_error += 1
            continue

        # Detect date range and instruments from the factor data
        dt_level = sample_series.index.get_level_values("datetime")
        inst_level = sample_series.index.get_level_values("instrument")
        fac_start = dt_level.min().strftime("%Y-%m-%d")
        fac_end = dt_level.max().strftime("%Y-%m-%d")
        instruments = inst_level.unique().tolist()

        logger.info(f"  Factor data range: {fac_start} ~ {fac_end}, instruments: {len(instruments)}")

        # Compute label for this specific scope
        try:
            label_df = compute_label_for_scope(
                instruments, fac_start, fac_end, label_expr
            )
            logger.info(f"  Label rows: {len(label_df)}")
            # Qlib returns (instrument, datetime) index; factor h5 uses (datetime, instrument).
            # Swap to match factor index order so intersection works.
            if isinstance(label_df.index, pd.MultiIndex):
                current_names = list(label_df.index.names)
                if current_names == ["instrument", "datetime"]:
                    label_df = label_df.swaplevel().sort_index()
                    logger.debug("  Label index swapped to (datetime, instrument)")
        except Exception as e:
            logger.warning(f"  Label computation failed: {e}")
            for fid in group_fids:
                skipped_error += 1
            continue

        # Build metric context for this scope
        ctx = MetricContext(
            provider_uri=data_config.get("provider_uri", ""),
            market=data_config.get("market", ""),
            start_time=fac_start,
            end_time=fac_end,
            label_expr=label_expr,
        ).to_dict()

        # Process each factor in this workspace
        for fid in group_fids:
            finfo = to_backfill[fid]
            factor_name = finfo.get("factor_name", fid)
            expr = finfo.get("factor_expression", "")

            fd_path = finfo.get("cache_location", {}).get("result_h5_path", "")
            if not fd_path or not Path(fd_path).exists():
                ws = finfo.get("cache_location", {}).get("workspace_path", "")
                fdir = finfo.get("cache_location", {}).get("factor_dir", "")
                alt = Path(ws) / fdir / "result.h5" if ws and fdir else None
                if alt and alt.exists():
                    fd_path = str(alt)
                else:
                    logger.warning(f"  [{factor_name}] result.h5 missing")
                    skipped_no_h5 += 1
                    continue

            try:
                factor_values = pd.read_hdf(fd_path)
            except Exception as e:
                logger.warning(f"  [{factor_name}] read error: {e}")
                skipped_error += 1
                continue

            if isinstance(factor_values, pd.DataFrame):
                if factor_values.shape[1] == 0:
                    skipped_no_h5 += 1
                    continue
                factor_series = factor_values.iloc[:, 0]
            else:
                factor_series = factor_values

            try:
                metrics_result = compute_factor_metrics(
                    factor_series, label_df["LABEL0"], metric_context=None
                )
            except Exception as e:
                logger.warning(f"  [{factor_name}] IC computation failed: {e}")
                skipped_error += 1
                continue

            fm = metrics_result.get("factor_metrics", {})
            quality = classify_quality(FactorICMetrics(**fm)) if fm else "unknown"

            if dry_run:
                logger.info(f"  [{factor_name}] would update: "
                           f"IC={fm.get('IC', 'N/A'):.6f}, "
                           f"Rank_IC={fm.get('Rank_IC', 'N/A'):.6f}, "
                           f"ICIR={fm.get('ICIR', 'N/A'):.6f}, "
                           f"Rank_ICIR={fm.get('Rank_ICIR', 'N/A'):.6f}, "
                           f"quality={quality}")
            else:
                factors[fid]["factor_metrics"] = fm
                factors[fid]["quality"] = quality
                factors[fid]["metric_context"] = ctx
                logger.info(f"  [{factor_name}] updated: IC={fm.get('IC', 'N/A'):.6f}, "
                           f"Rank_IC={fm.get('Rank_IC', 'N/A'):.6f}, quality={quality}")
                updated += 1

            if max_factors > 0 and updated >= max_factors:
                logger.info(f"Reached --max-factors limit ({max_factors}), stopping")
                break

        if max_factors > 0 and updated >= max_factors:
            break

    logger.info(f"\nSummary: {updated} updated, {skipped_no_h5} skipped (no data), "
               f"{skipped_error} skipped (error)")

    if not dry_run and updated > 0:
        library["metadata"]["last_updated"] = pd.Timestamp.now().isoformat()
        library["metadata"]["total_factors"] = len(factors)
        with open(lib_path, "w", encoding="utf-8") as f:
            json.dump(library, f, ensure_ascii=False, indent=2, default=str)
        logger.info(f"Library saved: {lib_path}")
    elif dry_run:
        logger.info("Dry run — no changes written")


def main():
    parser = argparse.ArgumentParser(description="Backfill per-factor IC metrics in factor library")
    parser.add_argument(
        "--library",
        default=str(project_root / "data" / "factorlib" / "all_factors_library.json"),
        help="Path to factor library JSON",
    )
    parser.add_argument(
        "--config",
        default=str(project_root / "configs" / "backtest.yaml"),
        help="Path to backtest YAML config",
    )
    parser.add_argument("--dry-run", action="store_true", help="Preview only, don't write")
    parser.add_argument("--force", action="store_true", help="Recompute even if factor_metrics exists")
    parser.add_argument(
        "--max-factors", type=int, default=0,
        help="Max factors to backfill (0 = unlimited)",
    )
    args = parser.parse_args()

    backfill_factor_metrics(
        library_path=args.library,
        config_path=args.config,
        dry_run=args.dry_run,
        force=args.force,
        max_factors=args.max_factors,
    )


if __name__ == "__main__":
    main()
