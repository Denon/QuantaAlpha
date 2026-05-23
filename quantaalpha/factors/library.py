"""
Factor library manager: save experiment output to unified JSON factor library.
Called from quantaalpha/pipeline/loop.py feedback step.
"""

import json
import hashlib
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

DEFAULT_FACTOR_CACHE_DIR = os.environ.get(
    "FACTOR_CACHE_DIR",
    "data/results/factor_cache",
)


class FactorLibraryManager:
    """Manage unified factor library (CRUD)."""

    def __init__(self, library_path: str):
        self.library_path = Path(library_path)
        self.data = self._load()

    def _load(self) -> dict:
        if self.library_path.exists():
            try:
                with open(self.library_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, Exception) as e:
                logger.warning(f"Factor library file corrupted, recreating: {e}")
        return {
            "metadata": {
                "created_at": datetime.now().isoformat(),
                "last_updated": datetime.now().isoformat(),
                "total_factors": 0,
                "version": "1.0",
            },
            "factors": {},
        }

    def _save(self):
        self.data["metadata"]["last_updated"] = datetime.now().isoformat()
        self.data["metadata"]["total_factors"] = len(self.data["factors"])
        self.library_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.library_path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2, default=str)

    @staticmethod
    def is_metric_stale(factor_info: dict, current_context: dict) -> bool:
        """Check if stored factor_metrics are stale vs current computation context.

        Compares stored metric_context (provider_uri, market, start_time, end_time,
        label_expr) against current_context. Returns True if any field differs,
        meaning the stored factor_metrics should be recomputed.
        """
        stored = factor_info.get("metric_context")
        if not stored:
            # No stored context — if factor_metrics exist, they were computed
            # without context and should be treated as fresh (legacy).
            return False
        for key in ("provider_uri", "market", "start_time", "end_time", "label_expr"):
            if stored.get(key) != current_context.get(key):
                logger.debug(
                    f"Stale factor_metrics detected [{factor_info.get('factor_id', '?')}]: "
                    f"stored {key}={stored.get(key)} vs current {key}={current_context.get(key)}"
                )
                return True
        return False

    def add_factors_from_experiment(
        self,
        experiment,
        experiment_id: str = "unknown",
        round_number: int = 0,
        hypothesis: Optional[str] = None,
        feedback: Any = None,
        initial_direction: Optional[str] = None,
        user_initial_direction: Optional[str] = None,
        planning_direction: Optional[str] = None,
        evolution_phase: str = "original",
        trajectory_id: str = "",
        parent_trajectory_ids: Optional[list] = None,
        factor_metrics_dict: Optional[dict] = None,
        metric_context: Optional[dict] = None,
    ):
        """Extract factors from a QlibFactorExperiment and write to library.

        Args:
            factor_metrics_dict: Optional dict mapping factor_id -> factor_metrics dict.
                If provided, each factor's entry contains per-factor IC metrics.
            metric_context: Optional dict with provider_uri, market, start_time, end_time,
                label_expr describing the context that produced factor_metrics.
        """
        if experiment is None:
            logger.warning("experiment is None, skip saving factors")
            return
        backtest_results = self._extract_backtest_results(experiment)
        feedback_dict = self._extract_feedback(feedback)
        sub_tasks = getattr(experiment, "sub_tasks", []) or []
        sub_workspaces = getattr(experiment, "sub_workspace_list", []) or []
        from quantaalpha.backtest.ic_metrics import classify_quality

        for idx, task in enumerate(sub_tasks):
            factor_name = getattr(task, "factor_name", getattr(task, "name", f"factor_{idx}"))
            factor_expr = getattr(task, "factor_expression", "")
            factor_desc = getattr(task, "factor_description", getattr(task, "description", ""))
            factor_form = getattr(task, "factor_formulation", "")

            factor_id = hashlib.md5(
                f"{factor_name}_{factor_expr}".encode()
            ).hexdigest()[:16]

            code = ""
            cache_location = {}
            if idx < len(sub_workspaces):
                ws = sub_workspaces[idx]
                code_dict = getattr(ws, "code_dict", {})
                code = "\n".join(
                    f"File: {fname}\n\n{content}"
                    for fname, content in code_dict.items()
                )
                ws_path = getattr(ws, "workspace_path", None)
                if ws_path:
                    ws_path = Path(ws_path)
                    workspace_suffix = ""
                    for part in ws_path.parts:
                        if part.startswith("workspace_"):
                            workspace_suffix = part.replace("workspace_", "")
                            break
                    h5_file = ws_path / "result.h5"
                    cache_location = {
                        "workspace_suffix": workspace_suffix,
                        "workspace_path": str(ws_path.parent),
                        "factor_dir": ws_path.name,
                    }
                    if h5_file.exists():
                        cache_location["result_h5_path"] = str(h5_file)
                    else:
                        logger.warning(
                            f"result.h5 missing for {factor_name} ({h5_file}), will recompute from expression in backtest"
                        )

            # Compute per-factor quality (uses factor_metrics exclusively)
            fm = (factor_metrics_dict or {}).get(factor_id, {})
            if fm:
                from quantaalpha.backtest.ic_metrics import FactorICMetrics
                quality = classify_quality(FactorICMetrics(**fm))
            else:
                quality = "unknown"

            factor_entry = {
                "factor_id": factor_id,
                "factor_name": factor_name,
                "factor_expression": factor_expr,
                "factor_implementation_code": code,
                "factor_description": factor_desc,
                "factor_formulation": factor_form,
                "cache_location": cache_location,
                "factor_metrics": fm,
                "quality": quality,
                "metric_context": metric_context or {},
                "experiment_backtest_results": backtest_results,
                "metadata": {
                    "experiment_id": experiment_id,
                    "round_number": round_number,
                    "evolution_phase": evolution_phase,
                    "trajectory_id": trajectory_id,
                    "parent_trajectory_ids": parent_trajectory_ids or [],
                    "hypothesis": str(hypothesis) if hypothesis else "",
                    "initial_direction": initial_direction or "",
                    "planning_direction": planning_direction or "",
                    "created_at": datetime.now().isoformat(),
                },
                "backtest_results": backtest_results,  # legacy compat
                "feedback": feedback_dict,
            }

            self.data["factors"][factor_id] = factor_entry

            if factor_expr and cache_location.get("result_h5_path"):
                self._sync_h5_to_md5_cache(factor_expr, cache_location["result_h5_path"],
                                            metric_context=metric_context)

        self._save()
        logger.info(
            f"Saved {len(sub_tasks)} factors to {self.library_path} (backtest_results: {len(backtest_results)} metrics)"
        )

    @staticmethod
    def _make_scoped_cache_key(expr: str, metric_context: Optional[dict] = None) -> str:
        """Create a scoped cache key from expression and optional context."""
        if metric_context:
            parts = "|".join([
                expr,
                metric_context.get("market", ""),
                metric_context.get("start_time", ""),
                metric_context.get("end_time", ""),
                metric_context.get("provider_uri", ""),
                metric_context.get("label_expr", ""),
            ])
        else:
            parts = expr
        return hashlib.md5(parts.encode()).hexdigest()

    @staticmethod
    def _sync_h5_to_md5_cache(factor_expression: str, h5_path: str,
                                cache_dir: Optional[str] = None,
                                metric_context: Optional[dict] = None) -> bool:
        """Sync factor values from result.h5 to scoped cache dir (.pkl). Returns True on success."""
        cache_dir = Path(cache_dir or DEFAULT_FACTOR_CACHE_DIR)
        h5_file = Path(h5_path)

        if not h5_file.exists():
            return False

        cache_key = FactorLibraryManager._make_scoped_cache_key(factor_expression, metric_context)
        pkl_file = cache_dir / f"{cache_key}.pkl"

        if pkl_file.exists():
            return True

        try:
            cache_dir.mkdir(parents=True, exist_ok=True)
            result = pd.read_hdf(str(h5_file))
            result.to_pickle(pkl_file)
            logger.debug(f"Synced factor cache -> {pkl_file.name}")
            return True
        except Exception as e:
            logger.debug(f"Sync factor cache failed [{h5_path}]: {e}")
            return False

    @staticmethod
    def check_cache_status(library_path: str,
                           cache_dir: Optional[str] = None) -> dict:
        """Check cache status for each factor in library. Returns:
            {
                "total": int,
                "h5_cached": int,
                "md5_cached": int,
                "need_compute": int,
                "factors": [ { "factor_id", "factor_name", "status" }, ... ]
            }
        """
        cache_dir = Path(cache_dir or DEFAULT_FACTOR_CACHE_DIR)

        with open(library_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        factors = data.get("factors", {})
        total = len(factors)
        h5_cached = 0
        md5_cached = 0
        need_compute = 0
        details = []

        for fid, finfo in factors.items():
            expr = finfo.get("factor_expression", "")
            cloc = finfo.get("cache_location", {})
            h5_path = cloc.get("result_h5_path", "")

            status = "need_compute"
            # Check h5 cache
            if h5_path and Path(h5_path).exists():
                status = "h5_cached"
                h5_cached += 1
            # Check MD5 cache (scoped first, then legacy)
            elif expr:
                mc = finfo.get("metric_context")
                scoped_key = FactorLibraryManager._make_scoped_cache_key(expr, mc) if mc else ""
                if scoped_key and (cache_dir / f"{scoped_key}.pkl").exists():
                    status = "md5_cached"
                    md5_cached += 1
                else:
                    legacy_key = hashlib.md5(expr.encode()).hexdigest()
                    if (cache_dir / f"{legacy_key}.pkl").exists():
                        status = "md5_cached"
                        md5_cached += 1

            if status == "need_compute":
                need_compute += 1

            details.append({
                "factor_id": fid,
                "factor_name": finfo.get("factor_name", fid),
                "status": status,
            })

        return {
            "total": total,
            "h5_cached": h5_cached,
            "md5_cached": md5_cached,
            "need_compute": need_compute,
            "factors": details,
        }

    @staticmethod
    def warm_cache_from_json(library_path: str,
                             cache_dir: Optional[str] = None) -> dict:
        """Walk factor library JSON and sync all available result.h5 to MD5 cache dir. Returns:
            { "total": int, "synced": int, "skipped": int, "failed": int,
              "already_cached": int, "no_source": int }
        """
        cache_dir_path = Path(cache_dir or DEFAULT_FACTOR_CACHE_DIR)

        with open(library_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        factors = data.get("factors", {})
        synced = 0
        skipped = 0
        failed = 0
        already_cached = 0
        no_source = 0

        for fid, finfo in factors.items():
            expr = finfo.get("factor_expression", "")
            cloc = finfo.get("cache_location", {})
            h5_path = cloc.get("result_h5_path", "")

            if not expr or not h5_path:
                no_source += 1
                skipped += 1
                continue

            mc = finfo.get("metric_context")
            scoped_key = FactorLibraryManager._make_scoped_cache_key(expr, mc) if mc else ""
            scoped_file = cache_dir_path / f"{scoped_key}.pkl" if scoped_key else None

            # Check scoped cache first, then legacy
            legacy_key = hashlib.md5(expr.encode()).hexdigest()
            legacy_file = cache_dir_path / f"{legacy_key}.pkl"

            if (scoped_file and scoped_file.exists()) or legacy_file.exists():
                already_cached += 1
                skipped += 1
                continue

            if not Path(h5_path).exists():
                failed += 1
                continue

            try:
                cache_dir_path.mkdir(parents=True, exist_ok=True)
                result = pd.read_hdf(str(h5_path))
                # Write scoped key if context available, else legacy
                target_file = scoped_file or legacy_file
                result.to_pickle(target_file)
                synced += 1
            except Exception:
                failed += 1

        return {
            "total": len(factors),
            "synced": synced,
            "skipped": skipped,
            "failed": failed,
            "already_cached": already_cached,
            "no_source": no_source,
        }

    @staticmethod
    def _extract_backtest_results(experiment) -> dict:
        """Extract backtest metrics from experiment.result (pandas Series) as dict."""
        result = getattr(experiment, "result", None)
        if result is None:
            return {}
        if isinstance(result, pd.Series):
            out = {}
            for key, val in result.items():
                # NaN/Inf -> None for JSON
                if isinstance(val, (float, np.floating)):
                    if np.isnan(val) or np.isinf(val):
                        out[str(key)] = None
                    else:
                        out[str(key)] = round(float(val), 8)
                else:
                    out[str(key)] = val
            return out

        if isinstance(result, pd.DataFrame):
            try:
                return {
                    str(k): round(float(v), 8) if isinstance(v, (float, np.floating)) and not np.isnan(v) else None
                    for k, v in result.iloc[:, 0].items()
                }
            except Exception:
                pass

        if isinstance(result, dict):
            return result

        return {}

    @staticmethod
    def _extract_feedback(feedback) -> dict:
        """Convert feedback object to serializable dict."""
        if feedback is None:
            return {}
        if isinstance(feedback, dict):
            return feedback

        out = {}
        for attr in ["observations", "hypothesis_evaluation", "decision", "reason",
                      "new_hypothesis", "feedback_str"]:
            val = getattr(feedback, attr, None)
            if val is not None:
                out[attr] = str(val) if not isinstance(val, (bool, int, float)) else val
        if not out:
            out["raw"] = str(feedback)
        return out
