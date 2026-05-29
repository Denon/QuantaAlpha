"""Walk-forward factor selection backtest mode.

Generates chronological folds, selects factors from in-sample windows only,
and evaluates the selected set on the next out-of-sample window.
"""

from __future__ import annotations

import copy
import json
import logging
from dataclasses import dataclass

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class WalkForwardConfig:
    enabled: bool = False
    start_time: str = ""
    end_time: str = ""
    selection_window_months: int = 6
    forward_window_months: int = 6
    step_months: int = 6
    selection_lag_days: int = 2
    internal_valid_ratio: float = 0.2
    top_k: int = 20
    min_selection_days: int = 10


@dataclass(frozen=True)
class WalkForwardFold:
    fold_id: int
    selection_start: pd.Timestamp
    selection_end: pd.Timestamp
    decision_date: pd.Timestamp
    forward_start: pd.Timestamp
    forward_end: pd.Timestamp
    train_start: pd.Timestamp
    train_end: pd.Timestamp
    valid_start: pd.Timestamp
    valid_end: pd.Timestamp
    test_start: pd.Timestamp
    test_end: pd.Timestamp


@dataclass(frozen=True)
class FoldResult:
    fold_id: int
    selection_start: str
    selection_end: str
    forward_start: str
    forward_end: str
    selected_factors: list[str]
    metrics: dict


@dataclass(frozen=True)
class WalkForwardResult:
    folds: list[FoldResult]
    aggregate_metrics: dict


def generate_walk_forward_folds(config: WalkForwardConfig) -> list[WalkForwardFold]:
    if config.step_months < config.forward_window_months:
        raise ValueError(
            f"step_months ({config.step_months}) must be >= forward_window_months "
            f"({config.forward_window_months}) to avoid overlapping forward windows"
        )
    start = pd.Timestamp(config.start_time)
    end = pd.Timestamp(config.end_time)
    selection_offset = pd.DateOffset(months=config.selection_window_months)
    forward_offset = pd.DateOffset(months=config.forward_window_months)
    step_offset = pd.DateOffset(months=config.step_months)

    folds: list[WalkForwardFold] = []
    selection_start = start
    fold_id = 1
    while True:
        decision_date = selection_start + selection_offset
        forward_start = decision_date
        forward_end = min(decision_date + forward_offset - pd.Timedelta(days=1), end)
        if forward_start > end:
            break

        selection_end = decision_date - pd.Timedelta(days=config.selection_lag_days)
        if selection_end <= selection_start:
            raise ValueError(
                f"selection_lag_days ({config.selection_lag_days}) leaves no usable "
                f"selection window: selection_start={selection_start.date()}, "
                f"selection_end={selection_end.date()}"
            )

        valid_days = max(1, int((selection_end - selection_start).days * config.internal_valid_ratio))
        valid_start = selection_end - pd.Timedelta(days=valid_days)
        train_end = valid_start - pd.Timedelta(days=1)
        if train_end < selection_start:
            train_end = selection_end
            valid_start = selection_end

        folds.append(
            WalkForwardFold(
                fold_id=fold_id,
                selection_start=selection_start,
                selection_end=selection_end,
                decision_date=decision_date,
                forward_start=forward_start,
                forward_end=forward_end,
                train_start=selection_start,
                train_end=train_end,
                valid_start=valid_start,
                valid_end=selection_end,
                test_start=forward_start,
                test_end=forward_end,
            )
        )

        fold_id += 1
        selection_start = selection_start + step_offset
        if selection_start + selection_offset > end:
            break

    return folds


def load_walk_forward_config(raw_config: dict) -> WalkForwardConfig:
    wf = raw_config.get("walk_forward", {})
    data = raw_config.get("data", {})
    return WalkForwardConfig(
        enabled=bool(wf.get("enabled", False)),
        start_time=wf.get("start_time") or data.get("start_time", ""),
        end_time=wf.get("end_time") or data.get("end_time", ""),
        selection_window_months=int(wf.get("selection_window_months", 6)),
        forward_window_months=int(wf.get("forward_window_months", 6)),
        step_months=int(wf.get("step_months", 6)),
        selection_lag_days=int(wf.get("selection_lag_days", 2)),
        internal_valid_ratio=float(wf.get("internal_valid_ratio", 0.2)),
        top_k=int(wf.get("top_k", 20)),
        min_selection_days=int(wf.get("min_selection_days", 10)),
    )


class WalkForwardBacktestRunner:
    def __init__(self, runner, config: WalkForwardConfig):
        self.runner = runner
        self.config = config

    def run(self, skip_uncached: bool = False) -> WalkForwardResult:
        from quantaalpha.backtest.precomputed_dataset import _normalize_multiindex

        self.runner._init_qlib()
        folds = generate_walk_forward_folds(self.config)
        features_df = self.runner.prepare_feature_frame(skip_uncached=skip_uncached)
        label_df = self.runner._compute_label(self.runner.config["dataset"]["label"])
        label_df = _normalize_multiindex(label_df, "label")
        label_series = label_df["LABEL0"]
        baseline_config = copy.deepcopy(self.runner.config)

        fold_results: list[FoldResult] = []
        for fold in folds:
            self.runner.config = copy.deepcopy(baseline_config)
            from quantaalpha.backtest.factor_selection import select_top_factors

            selection = select_top_factors(
                features_df=features_df,
                label_series=label_series,
                selection_start=str(fold.selection_start.date()),
                selection_end=str(fold.selection_end.date()),
                top_k=self.config.top_k,
                min_days=self.config.min_selection_days,
            )
            selected_names = [score.factor_name for score in selection.selected]
            self.runner._apply_backtest_window(
                train=(str(fold.train_start.date()), str(fold.train_end.date())),
                valid=(str(fold.valid_start.date()), str(fold.valid_end.date())),
                test=(str(fold.test_start.date()), str(fold.test_end.date())),
            )
            metrics = self.runner.run_feature_frame(
                features_df=features_df[selected_names],
                exp_name=f"{self.runner.config['experiment']['name']}_wf_{fold.fold_id:03d}",
                rec_name=f"{self.runner.config['experiment']['recorder']}_wf_{fold.fold_id:03d}",
                output_name=f"walk_forward_fold_{fold.fold_id:03d}",
            )
            fold_results.append(
                FoldResult(
                    fold_id=fold.fold_id,
                    selection_start=str(fold.selection_start.date()),
                    selection_end=str(fold.selection_end.date()),
                    forward_start=str(fold.forward_start.date()),
                    forward_end=str(fold.forward_end.date()),
                    selected_factors=selected_names,
                    metrics=metrics,
                )
            )

        aggregate = self._aggregate_metrics([fr.metrics for fr in fold_results])
        result = WalkForwardResult(folds=fold_results, aggregate_metrics=aggregate)
        self._save_result(result)
        return result

    def _aggregate_metrics(self, metrics_list: list[dict]) -> dict:
        aggregate = {"n_folds": len(metrics_list)}
        keys = sorted(
            {key for metrics in metrics_list for key in metrics if isinstance(metrics.get(key), (int, float))}
        )
        for key in keys:
            vals = [float(metrics[key]) for metrics in metrics_list if isinstance(metrics.get(key), (int, float))]
            if vals:
                aggregate[f"mean_{key}"] = float(np.mean(vals))
        return aggregate

    def _save_result(self, result: WalkForwardResult) -> None:
        output_dir = self.runner.config["experiment"].get("output_dir", "./backtest_v2_results")
        import os
        os.makedirs(output_dir, exist_ok=True)

        folds_path = os.path.join(output_dir, "walk_forward_folds.json")
        selected_path = os.path.join(output_dir, "walk_forward_selected_factors.csv")
        summary_path = os.path.join(output_dir, "walk_forward_summary.json")

        folds_data = []
        for fr in result.folds:
            folds_data.append(
                {
                    "fold_id": fr.fold_id,
                    "selection_start": fr.selection_start,
                    "selection_end": fr.selection_end,
                    "forward_start": fr.forward_start,
                    "forward_end": fr.forward_end,
                    "selected_factors": fr.selected_factors,
                    "metrics": fr.metrics,
                }
            )
        with open(folds_path, "w", encoding="utf-8") as f:
            json.dump(folds_data, f, ensure_ascii=False, indent=2)
        logger.info(f"Walk-forward folds saved: {folds_path}")

        selected_rows = []
        for fr in result.folds:
            for name in fr.selected_factors:
                selected_rows.append({"fold_id": fr.fold_id, "factor_name": name})
        pd.DataFrame(selected_rows, columns=["fold_id", "factor_name"]).to_csv(selected_path, index=False)
        logger.info(f"Walk-forward selected factors saved: {selected_path}")

        with open(summary_path, "w", encoding="utf-8") as f:
            json.dump(result.aggregate_metrics, f, ensure_ascii=False, indent=2)
        logger.info(f"Walk-forward summary saved: {summary_path}")
