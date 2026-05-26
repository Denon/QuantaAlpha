#!/usr/bin/env python3
"""
Compute IC metrics for size and beta from external data,
then import them into all_factors_library.json.

Usage:
    conda run -n rdagent python scripts/import_external_factors.py
"""

import hashlib
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import yaml

project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

# Paths
CONFIG_PATH = project_root / "configs" / "backtest.yaml"
LIBRARY_PATH = project_root / "data" / "factorlib" / "all_factors_library.json"
EXTERNAL_PATH = project_root / "data" / "external" / "factors_2016_2025.parquet"

FACTORS_META = {
    "size": {
        "name": "size",
        "description": "Log market cap: the natural logarithm of the company's total market capitalization",
        "expression": "external_data.size",
        "formulation": "ln(MarketCap)",
    },
    "beta": {
        "name": "beta",
        "description": (
            "The CAPM beta, slope coefficient from EW regression of stock return "
            "against float-cap-weighted market return over 252 trading days"
        ),
        "expression": "external_data.beta",
        "formulation": "Beta_252d_EW",
    },
}


def main():
    # 1. Load config
    with open(CONFIG_PATH) as f:
        config = yaml.safe_load(f)

    data_cfg = config["data"]
    dataset_cfg = config["dataset"]
    label_expr = dataset_cfg["label"]

    # 2. Init Qlib
    import os
    import qlib

    provider_uri = os.path.expanduser(data_cfg["provider_uri"])
    qlib.init(provider_uri=provider_uri, region=data_cfg.get("region", "cn"))
    logger.info(f"Qlib initialized: {provider_uri}")

    # 3. Load external data (size, beta)
    ext_df = pd.read_parquet(EXTERNAL_PATH)
    ext_df["date"] = pd.to_datetime(ext_df["date"])
    ext_df = ext_df.set_index(["date", "instrument"]).sort_index()
    ext_df.index.names = ["datetime", "instrument"]
    logger.info(f"External data loaded: {ext_df.shape}, {ext_df.columns.tolist()}")

    # 4. Compute label (forward return)
    from qlib.data import D

    instruments = D.instruments(data_cfg["market"])
    label_raw = D.features(
        instruments,
        [label_expr],
        start_time=data_cfg["start_time"],
        end_time=data_cfg["end_time"],
        freq="day",
    )
    label_raw.columns = ["LABEL0"]
    # Qlib returns (instrument, datetime) index → swap to (datetime, instrument)
    if list(label_raw.index.names) == ["instrument", "datetime"]:
        label_raw = label_raw.swaplevel().sort_index()
    logger.info(f"Label computed: {len(label_raw)} rows")

    # 5. Align and compute IC per factor
    from quantaalpha.backtest.ic_metrics import (
        compute_factor_metrics,
        MetricContext,
        classify_quality,
        FactorICMetrics,
    )

    ctx = MetricContext(
        provider_uri=data_cfg.get("provider_uri", ""),
        market=data_cfg.get("market", ""),
        start_time=data_cfg.get("start_time", ""),
        end_time=data_cfg.get("end_time", ""),
        label_expr=label_expr,
    )

    results = {}
    for col in ext_df.columns:
        factor_series = ext_df[col]
        logger.info(f"Computing IC for {col}...")
        metrics_result = compute_factor_metrics(
            factor_series, label_raw["LABEL0"], metric_context=ctx
        )
        fm = metrics_result.get("factor_metrics", {})
        quality = classify_quality(FactorICMetrics(**fm))
        results[col] = {**metrics_result, "quality": quality}
        logger.info(
            f"  {col}: IC={fm.get('IC', 'N/A'):.6f}, "
            f"Rank_IC={fm.get('Rank_IC', 'N/A'):.6f}, "
            f"ICIR={fm.get('ICIR', 'N/A'):.6f}, "
            f"Rank_ICIR={fm.get('Rank_ICIR', 'N/A'):.6f}, "
            f"quality={quality}"
        )

    # 6. Build library entries and merge into all_factors_library.json
    library_path = Path(LIBRARY_PATH)
    if library_path.exists():
        with open(library_path) as f:
            library = json.load(f)
    else:
        library = {
            "metadata": {
                "created_at": datetime.now().isoformat(),
                "last_updated": datetime.now().isoformat(),
                "total_factors": 0,
                "version": "1.0",
            },
            "factors": {},
        }

    factors = library["factors"]
    n_new = 0

    for col, result in results.items():
        meta = FACTORS_META[col]
        fm = result["factor_metrics"]
        mc = result.get("metric_context", {})
        quality = result["quality"]

        factor_id = hashlib.md5(f"{meta['name']}_{meta['expression']}".encode()).hexdigest()[:16]

        # Skip if already exists
        if factor_id in factors:
            logger.info(f"  {meta['name']} already in library, updating metrics...")
            existing = factors[factor_id]
            existing["factor_metrics"] = fm
            existing["quality"] = quality
            existing["metric_context"] = mc
            existing["metadata"]["last_updated"] = datetime.now().isoformat()
            continue

        entry = {
            "factor_id": factor_id,
            "factor_name": meta["name"],
            "factor_expression": meta["expression"],
            "factor_implementation_code": "",
            "factor_description": meta["description"],
            "factor_formulation": meta["formulation"],
            "cache_location": {},
            "factor_metrics": fm,
            "quality": quality,
            "metric_context": mc,
            "experiment_backtest_results": {},
            "metadata": {
                "experiment_id": "external_import",
                "round_number": 0,
                "evolution_phase": "external",
                "trajectory_id": "",
                "parent_trajectory_ids": [],
                "hypothesis": "",
                "initial_direction": "",
                "planning_direction": "",
                "created_at": datetime.now().isoformat(),
            },
            "backtest_results": {},
            "feedback": {},
        }
        factors[factor_id] = entry
        n_new += 1
        logger.info(f"  Added {meta['name']} to library (factor_id={factor_id})")

    # 7. Save
    library["metadata"]["last_updated"] = datetime.now().isoformat()
    library["metadata"]["total_factors"] = len(factors)
    with open(library_path, "w", encoding="utf-8") as f:
        json.dump(library, f, ensure_ascii=False, indent=2, default=str)

    logger.info(f"Done. {n_new} new factors added, {len(factors)} total in library.")
    print(f"\nResults saved to: {library_path}")


if __name__ == "__main__":
    main()
