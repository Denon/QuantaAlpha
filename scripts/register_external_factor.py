#!/usr/bin/env python3
"""
Register an external factor in the factor library.

Adds a factor entry with ``factor_source: "external"`` and
``evolution_phase: "manual_import"`` so that the AI mining pipeline's
FactorLoader recognises it alongside AI-generated factors.

Usage:
    python scripts/register_external_factor.py \\
        --name "market_cap_factor" \\
        --expression "\$market_cap" \\
        --description "Total market capitalization" \\
        --formulation "MC = P * S" \\
        --library data/factorlib/all_factors_library.json
"""

import argparse
import hashlib
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

project_root = Path(__file__).resolve().parents[1]


def _generate_factor_id(factor_name: str, factor_expr: str) -> str:
    """Deterministic factor ID from name and expression (matching FactorLoader)."""
    return hashlib.md5(f"{factor_name}_{factor_expr}".encode()).hexdigest()[:16]


def register_factor(
    library_path: str,
    factor_name: str,
    factor_expression: str,
    factor_description: str = "",
    factor_formulation: str = "",
    force: bool = False,
):
    """Add or overwrite an external factor in the library JSON."""

    lib_path = Path(library_path).expanduser()
    if not lib_path.exists():
        logger.error(f"Library not found: {lib_path}")
        return False

    with open(lib_path, "r", encoding="utf-8") as f:
        library = json.load(f)

    factors = library.get("factors", {})

    # Check for conflict by factor_name (not factor_id)
    existing_fid = None
    for fid, finfo in factors.items():
        if finfo.get("factor_name") == factor_name:
            existing_fid = fid
            break

    if existing_fid is not None:
        if not force:
            logger.error(
                f"Factor '{factor_name}' already exists (id={existing_fid}). "
                f"Use --force to overwrite."
            )
            return False
        logger.warning(f"Overwriting existing factor '{factor_name}' (id={existing_fid})")

    now_iso = datetime.now(timezone.utc).isoformat()

    factor_id = existing_fid or _generate_factor_id(factor_name, factor_expression)

    factor_entry = {
        "factor_id": factor_id,
        "factor_name": factor_name,
        "factor_expression": factor_expression,
        "factor_implementation_code": "",
        "factor_description": factor_description,
        "factor_formulation": factor_formulation,
        "cache_location": {},
        "factor_metrics": None,
        "quality": "unknown",
        "metric_context": {},
        "backtest_results": {},
        "feedback": {},
        "metadata": {
            "factor_source": "external",
            "evolution_phase": "manual_import",
            "created_at": now_iso,
        },
    }

    if existing_fid:
        # Preserve old factor_id for consistency (overwrite in place)
        factors[existing_fid] = factor_entry
    else:
        factors[factor_id] = factor_entry

    # Update library metadata
    metadata = library.setdefault("metadata", {})
    metadata["last_updated"] = now_iso
    metadata["total_factors"] = len(factors)

    with open(lib_path, "w", encoding="utf-8") as f:
        json.dump(library, f, ensure_ascii=False, indent=2, default=str)

    logger.info(
        f"Registered external factor: {factor_name} (id={factor_entry['factor_id']})"
    )
    logger.info(f"Library updated: {lib_path} ({len(factors)} total factors)")
    return True


def main():
    parser = argparse.ArgumentParser(
        description="Register an external factor in the factor library"
    )
    parser.add_argument(
        "--name", required=True,
        help="Factor name (must be unique unless --force)",
    )
    parser.add_argument(
        "--expression", required=True,
        help="Factor expression (e.g., '$market_cap')",
    )
    parser.add_argument(
        "--description", default="",
        help="Human-readable description of the factor",
    )
    parser.add_argument(
        "--formulation", default="",
        help="LaTeX or plain-text mathematical formulation",
    )
    parser.add_argument(
        "--library",
        default=str(project_root / "data" / "factorlib" / "all_factors_library.json"),
        help="Path to factor library JSON (default: data/factorlib/all_factors_library.json)",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Overwrite existing factor with the same name",
    )
    args = parser.parse_args()

    success = register_factor(
        library_path=args.library,
        factor_name=args.name,
        factor_expression=args.expression,
        factor_description=args.description,
        factor_formulation=args.formulation,
        force=args.force,
    )
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
