"""Tests for walk-forward fold generation, factor selection, precomputed dataset, and orchestration."""

import numpy as np
import pandas as pd

from quantaalpha.backtest.walk_forward import (
    WalkForwardConfig,
    WalkForwardFold,
    generate_walk_forward_folds,
    load_walk_forward_config,
)


def test_generate_half_year_folds_with_selection_lag():
    cfg = WalkForwardConfig(
        enabled=True,
        start_time="2015-01-01",
        end_time="2016-12-31",
        selection_window_months=6,
        forward_window_months=6,
        step_months=6,
        selection_lag_days=2,
        internal_valid_ratio=0.2,
        top_k=10,
        min_selection_days=10,
    )

    folds = generate_walk_forward_folds(cfg)

    assert len(folds) == 3
    assert folds[0].selection_start == pd.Timestamp("2015-01-01")
    assert folds[0].decision_date == pd.Timestamp("2015-07-01")
    assert folds[0].selection_end == pd.Timestamp("2015-06-29")
    assert folds[0].forward_start == pd.Timestamp("2015-07-01")
    assert folds[0].forward_end == pd.Timestamp("2015-12-31")
    assert folds[0].train_start == pd.Timestamp("2015-01-01")
    assert folds[0].valid_end == pd.Timestamp("2015-06-29")
    assert folds[0].test_start == pd.Timestamp("2015-07-01")


def test_step_smaller_than_forward_window_raises_error():
    cfg = WalkForwardConfig(
        enabled=True,
        start_time="2015-01-01",
        end_time="2016-12-31",
        selection_window_months=6,
        forward_window_months=6,
        step_months=3,  # smaller than forward_window_months
        selection_lag_days=2,
    )

    try:
        generate_walk_forward_folds(cfg)
        assert False, "Expected ValueError"
    except ValueError as e:
        assert "step_months" in str(e)


def test_selection_lag_exceeds_window_raises_error():
    cfg = WalkForwardConfig(
        enabled=True,
        start_time="2015-01-01",
        end_time="2015-12-31",
        selection_window_months=6,
        forward_window_months=6,
        step_months=6,
        selection_lag_days=200,  # more days than in the window
        internal_valid_ratio=0.2,
    )

    try:
        generate_walk_forward_folds(cfg)
        assert False, "Expected ValueError"
    except ValueError as e:
        assert "selection_lag_days" in str(e)


def test_load_walk_forward_config_uses_data_range_defaults():
    config = {
        "data": {"start_time": "2016-01-01", "end_time": "2025-12-26"},
        "walk_forward": {"enabled": True, "top_k": 5},
    }

    cfg = load_walk_forward_config(config)

    assert cfg.enabled is True
    assert cfg.start_time == "2016-01-01"
    assert cfg.end_time == "2025-12-26"
    assert cfg.top_k == 5
    assert cfg.min_selection_days == 10


def test_load_walk_forward_config_disabled_by_default():
    config = {}

    cfg = load_walk_forward_config(config)

    assert cfg.enabled is False


def test_forward_window_capped_at_global_end_time():
    cfg = WalkForwardConfig(
        enabled=True,
        start_time="2015-01-01",
        end_time="2015-09-30",
        selection_window_months=6,
        forward_window_months=6,
        step_months=6,
        selection_lag_days=2,
    )

    folds = generate_walk_forward_folds(cfg)

    assert len(folds) == 1
    assert folds[0].forward_end == pd.Timestamp("2015-09-30")


def test_output_files_written_even_when_no_factors_selected(tmp_path):
    from unittest.mock import MagicMock

    from quantaalpha.backtest.walk_forward import WalkForwardBacktestRunner, WalkForwardConfig

    dates = pd.date_range("2015-01-01", periods=260, freq="D")
    instruments = ["A"]
    idx = pd.MultiIndex.from_product([dates, instruments], names=["datetime", "instrument"])
    label = pd.Series(np.ones(len(idx)), index=idx, name="LABEL0")
    features = pd.DataFrame({"f": [np.nan] * len(idx)}, index=idx)

    runner = MagicMock()
    runner.config = {
        "experiment": {"name": "wf", "recorder": "rec", "output_dir": str(tmp_path)},
        "dataset": {"label": "LABEL0"},
    }
    runner.prepare_feature_frame.return_value = features
    runner._compute_label.return_value = pd.DataFrame({"LABEL0": label})
    runner.run_feature_frame.return_value = {"Rank IC": 0.0}

    cfg = WalkForwardConfig(
        enabled=True,
        start_time="2015-01-01",
        end_time="2015-09-30",
        selection_window_months=3,
        forward_window_months=3,
        step_months=3,
        selection_lag_days=2,
        top_k=1,
        min_selection_days=2,
    )

    wf = WalkForwardBacktestRunner(runner, cfg)
    wf.run()

    csv_path = tmp_path / "walk_forward_selected_factors.csv"
    assert csv_path.exists(), f"Expected {csv_path} to exist even with no selected factors"
    folds_path = tmp_path / "walk_forward_folds.json"
    assert folds_path.exists()
    summary_path = tmp_path / "walk_forward_summary.json"
    assert summary_path.exists()


# --- Precomputed dataset tests ---


def test_build_precomputed_dataset_aligns_features_and_label():
    from quantaalpha.backtest.precomputed_dataset import build_precomputed_dataset

    dates = pd.date_range("2024-01-01", periods=5, freq="D")
    instruments = ["A", "B", "C"]
    idx = pd.MultiIndex.from_product([dates, instruments], names=["datetime", "instrument"])
    features = pd.DataFrame({"factor_a": np.arange(len(idx), dtype=float)}, index=idx)
    label = pd.DataFrame({"LABEL0": np.arange(len(idx), dtype=float) / 100}, index=idx)
    segments = {
        "train": ["2024-01-01", "2024-01-03"],
        "valid": ["2024-01-04", "2024-01-04"],
        "test": ["2024-01-05", "2024-01-05"],
    }

    dataset = build_precomputed_dataset(features, label, segments)
    fetched = dataset.handler.fetch(col_set="feature")

    assert list(fetched.columns) == ["factor_a"]
    assert len(fetched) == len(idx)


def test_build_precomputed_dataset_handles_instrument_first_index():
    from quantaalpha.backtest.precomputed_dataset import build_precomputed_dataset

    dates = pd.date_range("2024-01-01", periods=3, freq="D")
    instruments = ["A", "B"]
    idx = pd.MultiIndex.from_product([instruments, dates], names=["instrument", "datetime"])
    features = pd.DataFrame({"f": np.arange(len(idx), dtype=float)}, index=idx)
    label = pd.DataFrame({"LABEL0": np.arange(len(idx), dtype=float) / 10}, index=idx)
    segments = {
        "train": ["2024-01-01", "2024-01-02"],
        "valid": ["2024-01-03", "2024-01-03"],
        "test": ["2024-01-03", "2024-01-03"],
    }

    dataset = build_precomputed_dataset(features, label, segments)
    fetched = dataset.handler.fetch(col_set="feature")

    assert "f" in list(fetched.columns)
    assert len(fetched) == len(idx)


# --- BacktestRunner helper tests ---


def test_apply_fold_config_sets_segments_and_backtest_range(tmp_path):
    from quantaalpha.backtest.runner import BacktestRunner

    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
data:
  provider_uri: ~/.qlib/qlib_data/cn_data
  region: cn
  market: csi300
  start_time: '2015-01-01'
  end_time: '2015-12-31'
dataset:
  label: Ref($close, -2) / Ref($close, -1) - 1
  segments:
    train: ['2015-01-01', '2015-03-31']
    valid: ['2015-04-01', '2015-06-30']
    test: ['2015-07-01', '2015-12-31']
backtest:
  backtest:
    start_time: '2015-07-01'
    end_time: '2015-12-31'
experiment:
  name: test
  recorder: rec
model:
  type: lgb
  params: {}
factor_source:
  type: alpha158_20
""",
        encoding="utf-8",
    )
    runner = BacktestRunner(str(config_path))

    runner._apply_backtest_window(
        train=("2015-01-01", "2015-05-15"),
        valid=("2015-05-16", "2015-06-29"),
        test=("2015-07-01", "2015-12-31"),
    )

    assert runner.config["dataset"]["segments"]["train"] == ["2015-01-01", "2015-05-15"]
    assert runner.config["backtest"]["backtest"]["start_time"] == "2015-07-01"


# --- WalkForwardBacktestRunner orchestration test ---


def test_walk_forward_runner_selects_and_runs_each_fold(tmp_path):
    from unittest.mock import MagicMock

    from quantaalpha.backtest.walk_forward import WalkForwardBacktestRunner, WalkForwardConfig

    dates = pd.date_range("2015-01-01", periods=260, freq="D")
    instruments = ["A", "B", "C", "D", "E"]
    idx = pd.MultiIndex.from_product([dates, instruments], names=["datetime", "instrument"])
    label = pd.Series(np.tile([1, 2, 3, 4, 5], len(dates)), index=idx, name="LABEL0")
    weak_values = np.resize(np.array([5, 1, 4, 2, 3], dtype=float), len(idx))
    features = pd.DataFrame({"good": label + 0.01, "bad": weak_values}, index=idx)

    runner = MagicMock()
    runner.config = {
        "experiment": {"name": "wf", "recorder": "rec", "output_dir": str(tmp_path)},
        "dataset": {"label": "LABEL0"},
    }
    runner.prepare_feature_frame.return_value = features
    runner._compute_label.return_value = pd.DataFrame({"LABEL0": label})
    runner.run_feature_frame.return_value = {"Rank IC": 0.03, "annualized_return": 0.1}

    cfg = WalkForwardConfig(
        enabled=True,
        start_time="2015-01-01",
        end_time="2015-12-31",
        selection_window_months=6,
        forward_window_months=6,
        step_months=6,
        selection_lag_days=2,
        internal_valid_ratio=0.2,
        top_k=1,
    )

    wf = WalkForwardBacktestRunner(runner, cfg)
    result = wf.run()

    assert len(result.folds) == 1
    assert result.folds[0].selected_factors == ["good"]
    runner.run_feature_frame.assert_called_once()


def test_walk_forward_runner_restores_config_between_folds(tmp_path):
    from unittest.mock import MagicMock

    from quantaalpha.backtest.walk_forward import WalkForwardBacktestRunner

    dates = pd.date_range("2015-01-01", periods=500, freq="D")
    instruments = ["A", "B", "C"]
    idx = pd.MultiIndex.from_product([dates, instruments], names=["datetime", "instrument"])
    label = pd.Series(np.random.randn(len(idx)), index=idx, name="LABEL0")
    features = pd.DataFrame({"f1": label + 0.01, "f2": label - 0.01}, index=idx)

    runner = MagicMock()
    original_config = {
        "experiment": {"name": "wf", "recorder": "rec", "output_dir": str(tmp_path)},
        "dataset": {"label": "LABEL0", "segments": {"train": ["a", "b"], "valid": ["c", "d"], "test": ["e", "f"]}},
        "backtest": {"backtest": {"start_time": "x", "end_time": "y"}},
    }
    runner.config = original_config
    runner.prepare_feature_frame.return_value = features
    runner._compute_label.return_value = pd.DataFrame({"LABEL0": label})
    runner.run_feature_frame.return_value = {"Rank IC": 0.02}

    # Wire _apply_backtest_window so it actually mutates config like the real method
    def apply_window(train, valid, test):
        runner.config["dataset"]["segments"] = {
            "train": [train[0], train[1]],
            "valid": [valid[0], valid[1]],
            "test": [test[0], test[1]],
        }
        runner.config["backtest"]["backtest"]["start_time"] = test[0]
        runner.config["backtest"]["backtest"]["end_time"] = test[1]

    runner._apply_backtest_window = apply_window

    # Record the config seen by each run_feature_frame call
    configs_seen = []

    def capture_config(*args, **kwargs):
        configs_seen.append({
            "segments": dict(runner.config["dataset"]["segments"]),
            "backtest_start": runner.config["backtest"]["backtest"]["start_time"],
        })
        return {"Rank IC": 0.02}

    runner.run_feature_frame = capture_config

    cfg = WalkForwardConfig(
        enabled=True,
        start_time="2015-01-01",
        end_time="2016-12-31",
        selection_window_months=6,
        forward_window_months=6,
        step_months=6,
        selection_lag_days=2,
        internal_valid_ratio=0.2,
        top_k=2,
        min_selection_days=2,
    )

    wf = WalkForwardBacktestRunner(runner, cfg)
    result = wf.run()

    assert len(result.folds) > 1
    # Each fold should have seen a different config
    backtest_starts = [c["backtest_start"] for c in configs_seen]
    assert len(set(backtest_starts)) == len(backtest_starts), (
        f"Expected each fold to have a unique backtest start, got: {backtest_starts}"
    )
