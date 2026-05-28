# Walk-Forward Factor Selection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a walk-forward, online factor selection backtest mode that selects factors from only past data and evaluates the selected set on the next out-of-sample window.

**Architecture:** Keep `BacktestRunner` as the single-window executor and add a separate walk-forward orchestrator around it. The new mode will precompute/load candidate factor values once, generate chronological folds, score factors inside each selection window, run the existing Qlib model/backtest on the next forward window, and aggregate fold-level results. The default single-window backtest path remains unchanged.

**Tech Stack:** Python 3.10+, pandas, numpy, Qlib, PyYAML, pytest.

---

## Current Context

- `quantaalpha/backtest/runner.py` runs one static backtest: load factors, compute custom factors, create a fixed dataset from `dataset.segments`, train LightGBM, run Qlib portfolio backtest, and save one metrics file.
- `quantaalpha/backtest/factor_loader.py` already supports exact-expression deduplication, metric-based sorting, and `max_factors`, but the ranking uses stored full-context metrics rather than a rolling in-sample window.
- `quantaalpha/backtest/ic_metrics.py` already computes daily cross-sectional Pearson IC and Rank IC between one factor and the forward-return label.
- `configs/backtest.yaml` has fixed `data.start_time`, `data.end_time`, `dataset.segments`, and `backtest.backtest.start_time/end_time`.

## Decisions

1. Walk-forward mode is opt-in through config and CLI. Existing static backtests must behave exactly as before when `walk_forward.enabled` is false.
2. Factor selection must use only dates whose labels are observable before the fold decision date. Add `selection_lag_days` with a default of `2` because the current label uses future references.
3. V1 scoring uses existing robust metrics: `abs(Rank_IC)` first, `abs(Rank_ICIR)` second, then valid-day count. This matches the current factor-quality direction and keeps the first implementation focused.
4. V1 does not add market-regime detection. The design leaves scoring pluggable so regime-aware selection can be added later.
5. Walk-forward mode always builds a precomputed feature frame for candidate factors. This gives deterministic per-window selection and avoids repeatedly loading the same Qlib features for every fold.

## File Structure

- Create `quantaalpha/backtest/walk_forward.py`
  - Dataclasses: `WalkForwardConfig`, `WalkForwardFold`, `FoldResult`, `WalkForwardResult`.
  - Functions: `generate_walk_forward_folds`, `load_walk_forward_config`.
  - Class: `WalkForwardBacktestRunner`.
- Create `quantaalpha/backtest/factor_selection.py`
  - Dataclasses: `FactorScore`, `FactorSelectionResult`.
  - Functions: `score_factor_window`, `select_top_factors`.
- Create `quantaalpha/backtest/precomputed_dataset.py`
  - Move reusable precomputed dataset construction out of the inner class in `runner.py`.
  - Functions: `normalize_multiindex`, `build_precomputed_dataset`.
  - Class: `PrecomputedDataHandler`.
- Modify `quantaalpha/backtest/runner.py`
  - Reuse `precomputed_dataset.py`.
  - Add helpers to prepare one full feature frame and run a backtest from a selected feature frame.
- Modify `quantaalpha/backtest/run_backtest.py`
  - Add `--walk-forward` flag and dispatch to `WalkForwardBacktestRunner` when enabled.
- Modify `configs/backtest.yaml`
  - Add a disabled-by-default `walk_forward` block with sane half-year defaults.
- Modify `quantaalpha/backtest/README.md`
  - Document the walk-forward workflow, output files, and leakage rules.
- Add tests:
  - `tests/test_walk_forward.py`
  - `tests/test_factor_selection.py`

---

### Task 1: Add Walk-Forward Config And Fold Generation

**Files:**
- Create: `quantaalpha/backtest/walk_forward.py`
- Test: `tests/test_walk_forward.py`

- [ ] **Step 1: Write failing tests for fold generation**

```python
import pandas as pd

from quantaalpha.backtest.walk_forward import WalkForwardConfig, generate_walk_forward_folds


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
```

- [ ] **Step 2: Run the test and verify it fails**

Run: `.venv/bin/pytest tests/test_walk_forward.py::test_generate_half_year_folds_with_selection_lag -q`

Expected: FAIL with `ModuleNotFoundError` or missing symbol errors.

- [ ] **Step 3: Implement config and fold generation**

```python
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


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


def generate_walk_forward_folds(config: WalkForwardConfig) -> list[WalkForwardFold]:
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
            raise ValueError("selection_lag_days leaves no usable selection window")

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
```

- [ ] **Step 4: Run the fold tests**

Run: `.venv/bin/pytest tests/test_walk_forward.py -q`

Expected: PASS for the new fold-generation test.

- [ ] **Step 5: Commit**

```bash
git add quantaalpha/backtest/walk_forward.py tests/test_walk_forward.py
git commit -m "feat: add walk-forward fold generation"
```

---

### Task 2: Add Window-Aware Factor Scoring

**Files:**
- Create: `quantaalpha/backtest/factor_selection.py`
- Test: `tests/test_factor_selection.py`

- [ ] **Step 1: Write failing tests for factor scoring and top-k selection**

```python
import numpy as np
import pandas as pd

from quantaalpha.backtest.factor_selection import select_top_factors


def _series(name: str, values: list[float]) -> pd.Series:
    dates = pd.date_range("2024-01-01", periods=4, freq="D")
    instruments = ["A", "B", "C", "D"]
    idx = pd.MultiIndex.from_product([dates, instruments], names=["datetime", "instrument"])
    repeated = np.resize(np.array(values, dtype=float), len(idx))
    return pd.Series(repeated, index=idx, name=name)


def test_select_top_factors_uses_only_requested_window():
    label = _series("LABEL0", [1.0, 2.0, 3.0, 4.0])
    features = pd.DataFrame(
        {
            "strong": label + 0.001,
            "weak": _series("weak", [4.0, 1.0, 3.0, 2.0]),
            "empty": np.nan,
        }
    )

    result = select_top_factors(
        features_df=features,
        label_series=label,
        selection_start="2024-01-01",
        selection_end="2024-01-04",
        top_k=2,
        min_days=2,
    )

    assert [score.factor_name for score in result.selected] == ["strong", "weak"]
    assert "empty" in result.rejected
```

- [ ] **Step 2: Run the test and verify it fails**

Run: `.venv/bin/pytest tests/test_factor_selection.py -q`

Expected: FAIL because `factor_selection.py` does not exist.

- [ ] **Step 3: Implement scoring**

```python
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from quantaalpha.backtest.ic_metrics import compute_factor_metrics


@dataclass(frozen=True)
class FactorScore:
    factor_name: str
    rank_ic: float
    rank_icir: float
    ic: float
    icir: float
    n_days: int
    n_obs: int

    @property
    def sort_key(self) -> tuple:
        return (-abs(self.rank_ic), -abs(self.rank_icir), -self.n_days, self.factor_name)


@dataclass(frozen=True)
class FactorSelectionResult:
    selected: list[FactorScore]
    rejected: dict[str, str]
    all_scores: list[FactorScore]


def _window_slice(series: pd.Series, start: str, end: str) -> pd.Series:
    dates = series.index.get_level_values("datetime")
    mask = (dates >= pd.Timestamp(start)) & (dates <= pd.Timestamp(end))
    return series.loc[mask]


def score_factor_window(
    factor_name: str,
    factor_series: pd.Series,
    label_series: pd.Series,
    selection_start: str,
    selection_end: str,
    min_days: int,
) -> FactorScore | None:
    factor_window = _window_slice(factor_series, selection_start, selection_end)
    label_window = _window_slice(label_series, selection_start, selection_end)
    result = compute_factor_metrics(factor_window, label_window)
    metrics = result["factor_metrics"]
    if metrics["n_days"] < min_days:
        return None
    return FactorScore(
        factor_name=factor_name,
        rank_ic=float(metrics["Rank_IC"]),
        rank_icir=float(metrics["Rank_ICIR"]),
        ic=float(metrics["IC"]),
        icir=float(metrics["ICIR"]),
        n_days=int(metrics["n_days"]),
        n_obs=int(metrics["n_obs"]),
    )


def select_top_factors(
    features_df: pd.DataFrame,
    label_series: pd.Series,
    selection_start: str,
    selection_end: str,
    top_k: int,
    min_days: int = 10,
) -> FactorSelectionResult:
    scores: list[FactorScore] = []
    rejected: dict[str, str] = {}
    for factor_name in features_df.columns:
        score = score_factor_window(
            factor_name=factor_name,
            factor_series=features_df[factor_name],
            label_series=label_series,
            selection_start=selection_start,
            selection_end=selection_end,
            min_days=min_days,
        )
        if score is None:
            rejected[factor_name] = "insufficient_valid_days"
        else:
            scores.append(score)

    scores.sort(key=lambda score: score.sort_key)
    selected = scores if top_k == 0 else scores[:top_k]
    return FactorSelectionResult(selected=selected, rejected=rejected, all_scores=scores)
```

- [ ] **Step 4: Run factor-selection tests**

Run: `.venv/bin/pytest tests/test_factor_selection.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add quantaalpha/backtest/factor_selection.py tests/test_factor_selection.py
git commit -m "feat: add rolling factor selection scoring"
```

---

### Task 3: Extract Precomputed Dataset Builder

**Files:**
- Create: `quantaalpha/backtest/precomputed_dataset.py`
- Modify: `quantaalpha/backtest/runner.py`
- Test: `tests/test_walk_forward.py`

- [ ] **Step 1: Write a test for reusable precomputed dataset creation**

```python
import numpy as np
import pandas as pd

from quantaalpha.backtest.precomputed_dataset import build_precomputed_dataset


def test_build_precomputed_dataset_aligns_features_and_label():
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
```

- [ ] **Step 2: Run the test and verify it fails**

Run: `.venv/bin/pytest tests/test_walk_forward.py::test_build_precomputed_dataset_aligns_features_and_label -q`

Expected: FAIL because `precomputed_dataset.py` does not exist.

- [ ] **Step 3: Move the current inner `PrecomputedDataHandler` logic**

Create `precomputed_dataset.py` using the normalization, alignment, feature rank normalization, label rank normalization, and `DatasetH` construction currently embedded in `BacktestRunner._create_dataset_with_computed_factors`.

Important behavior to preserve:
- Accept `(datetime, instrument)` and `(instrument, datetime)` index order.
- Drop rows without labels.
- Fill feature NaN and infinite values with zero before cross-sectional rank normalization.
- Return a Qlib `DatasetH` with the supplied `segments`.

- [ ] **Step 4: Modify `BacktestRunner._create_dataset_with_computed_factors` to delegate**

Replace the inner handler block with:

```python
from quantaalpha.backtest.precomputed_dataset import build_precomputed_dataset

return build_precomputed_dataset(
    features_df=features_df,
    label_df=label_df,
    segments=dataset_config["segments"],
)
```

- [ ] **Step 5: Run metric and dataset tests**

Run: `.venv/bin/pytest tests/test_factor_metrics.py tests/test_walk_forward.py -q`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add quantaalpha/backtest/precomputed_dataset.py quantaalpha/backtest/runner.py tests/test_walk_forward.py
git commit -m "refactor: extract precomputed dataset builder"
```

---

### Task 4: Add Runner Helpers For Prepared Feature Frames

**Files:**
- Modify: `quantaalpha/backtest/runner.py`
- Test: `tests/test_walk_forward.py`

- [ ] **Step 1: Write tests for selected feature frame execution seams**

Use mocks for Qlib calls so the test only verifies config wiring and column selection.

```python
import copy
import numpy as np
import pandas as pd

from quantaalpha.backtest.runner import BacktestRunner


def test_apply_fold_config_sets_segments_and_backtest_range(tmp_path):
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
    original = copy.deepcopy(runner.config)

    runner._apply_backtest_window(
        train=("2015-01-01", "2015-05-15"),
        valid=("2015-05-16", "2015-06-29"),
        test=("2015-07-01", "2015-12-31"),
    )

    assert runner.config["dataset"]["segments"]["train"] == ["2015-01-01", "2015-05-15"]
    assert runner.config["backtest"]["backtest"]["start_time"] == "2015-07-01"
    assert original["dataset"]["segments"]["train"] == ["2015-01-01", "2015-03-31"]
```

- [ ] **Step 2: Run the test and verify it fails**

Run: `.venv/bin/pytest tests/test_walk_forward.py::test_apply_fold_config_sets_segments_and_backtest_range -q`

Expected: FAIL because `_apply_backtest_window` does not exist.

- [ ] **Step 3: Add runner helpers**

Add these methods to `BacktestRunner`:

```python
def _apply_backtest_window(self, train: tuple[str, str], valid: tuple[str, str], test: tuple[str, str]) -> None:
    self.config["dataset"]["segments"] = {
        "train": [train[0], train[1]],
        "valid": [valid[0], valid[1]],
        "test": [test[0], test[1]],
    }
    self.config["backtest"]["backtest"]["start_time"] = test[0]
    self.config["backtest"]["backtest"]["end_time"] = test[1]


def _create_dataset_from_feature_frame(self, features_df: pd.DataFrame):
    label_df = self._compute_label(self.config["dataset"]["label"])
    from quantaalpha.backtest.precomputed_dataset import build_precomputed_dataset
    return build_precomputed_dataset(
        features_df=features_df,
        label_df=label_df,
        segments=self.config["dataset"]["segments"],
    )


def run_feature_frame(self, features_df: pd.DataFrame, exp_name: str, rec_name: str, output_name: str | None = None) -> dict:
    dataset = self._create_dataset_from_feature_frame(features_df)
    return self._train_and_backtest(dataset, exp_name, rec_name, output_name=output_name)
```

- [ ] **Step 4: Add helper to prepare all candidate features once**

Add:

```python
def prepare_feature_frame(self, custom_factors: list[dict] | None = None, skip_uncached: bool = False) -> pd.DataFrame:
    factor_expressions, loaded_custom = self._load_factors()
    custom_to_compute = custom_factors if custom_factors is not None else loaded_custom
    frames = []
    if factor_expressions:
        qlib_features = self._load_qlib_factors(factor_expressions)
        if qlib_features is not None and not qlib_features.empty:
            frames.append(qlib_features)
    if custom_to_compute:
        computed = self._compute_custom_factors(custom_to_compute, skip_compute=skip_uncached)
        if computed is not None and not computed.empty:
            frames.append(computed)
    from quantaalpha.backtest.external_data import load_external_data
    external_df = load_external_data(self.config)
    if external_df is not None and not external_df.empty:
        frames.append(external_df)
    if not frames:
        raise ValueError("No candidate factor features available")
    return pd.concat(frames, axis=1).loc[:, lambda df: ~df.columns.duplicated()]
```

- [ ] **Step 5: Run tests**

Run: `.venv/bin/pytest tests/test_walk_forward.py tests/test_factor_metrics.py -q`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add quantaalpha/backtest/runner.py tests/test_walk_forward.py
git commit -m "feat: add prepared feature frame backtest helpers"
```

---

### Task 5: Implement WalkForwardBacktestRunner Orchestration

**Files:**
- Modify: `quantaalpha/backtest/walk_forward.py`
- Test: `tests/test_walk_forward.py`

- [ ] **Step 1: Write orchestration test with mocked single-fold execution**

```python
from unittest.mock import MagicMock

import numpy as np
import pandas as pd

from quantaalpha.backtest.walk_forward import WalkForwardBacktestRunner, WalkForwardConfig


def test_walk_forward_runner_selects_and_runs_each_fold(tmp_path):
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
```

- [ ] **Step 2: Run the test and verify it fails**

Run: `.venv/bin/pytest tests/test_walk_forward.py::test_walk_forward_runner_selects_and_runs_each_fold -q`

Expected: FAIL because `WalkForwardBacktestRunner` is not implemented.

- [ ] **Step 3: Implement the orchestrator**

Behavior:
- Build folds from config.
- Call `runner.prepare_feature_frame(...)` once.
- Compute label once over the configured data range.
- For each fold:
  - Select factors using `select_top_factors`.
  - Apply fold train/valid/test/backtest ranges.
  - Run `runner.run_feature_frame(features_df[selected_names], ...)`.
  - Store selected factors, factor scores, and returned metrics.
- Save:
  - `walk_forward_folds.json`
  - `walk_forward_selected_factors.csv`
  - `walk_forward_summary.json`

Implementation shape:

```python
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


class WalkForwardBacktestRunner:
    def __init__(self, runner, config: WalkForwardConfig):
        self.runner = runner
        self.config = config

    def run(self, skip_uncached: bool = False) -> WalkForwardResult:
        folds = generate_walk_forward_folds(self.config)
        features_df = self.runner.prepare_feature_frame(skip_uncached=skip_uncached)
        label_df = self.runner._compute_label(self.runner.config["dataset"]["label"])
        label_series = label_df["LABEL0"]

        fold_results = []
        for fold in folds:
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
```

- [ ] **Step 4: Implement aggregate metrics**

Aggregate numeric metrics by mean and include fold count:

```python
def _aggregate_metrics(self, metrics_list: list[dict]) -> dict:
    aggregate = {"n_folds": len(metrics_list)}
    keys = sorted({key for metrics in metrics_list for key in metrics if isinstance(metrics.get(key), (int, float))})
    for key in keys:
        vals = [float(metrics[key]) for metrics in metrics_list if isinstance(metrics.get(key), (int, float))]
        if vals:
            aggregate[f"mean_{key}"] = float(np.mean(vals))
    return aggregate
```

- [ ] **Step 5: Run orchestration tests**

Run: `.venv/bin/pytest tests/test_walk_forward.py tests/test_factor_selection.py -q`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add quantaalpha/backtest/walk_forward.py tests/test_walk_forward.py
git commit -m "feat: add walk-forward backtest runner"
```

---

### Task 6: Add Config, CLI, And Documentation

**Files:**
- Modify: `configs/backtest.yaml`
- Modify: `quantaalpha/backtest/run_backtest.py`
- Modify: `quantaalpha/backtest/README.md`
- Test: `tests/test_walk_forward.py`

- [ ] **Step 1: Add config defaults**

Add this block to `configs/backtest.yaml`:

```yaml
walk_forward:
  enabled: false
  start_time: "2016-01-01"
  end_time: "2025-12-26"
  selection_window_months: 6
  forward_window_months: 6
  step_months: 6
  selection_lag_days: 2
  internal_valid_ratio: 0.2
  top_k: 20
  min_selection_days: 10
```

- [ ] **Step 2: Add config loader tests**

```python
from quantaalpha.backtest.walk_forward import load_walk_forward_config


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
```

- [ ] **Step 3: Implement config loading**

```python
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
```

- [ ] **Step 4: Add CLI dispatch**

In `run_backtest.py`, add:

```python
parser.add_argument("--walk-forward", action="store_true", help="Run walk-forward factor selection backtest")
```

Before the static `runner.run(...)` branch, dispatch:

```python
if args.walk_forward or runner.config.get("walk_forward", {}).get("enabled", False):
    from quantaalpha.backtest.walk_forward import WalkForwardBacktestRunner, load_walk_forward_config

    wf_config = load_walk_forward_config(runner.config)
    WalkForwardBacktestRunner(runner, wf_config).run(skip_uncached=args.skip_uncached)
else:
    runner.run(...)
```

- [ ] **Step 5: Document usage**

Add a README section with:

```bash
python -m quantaalpha.backtest.run_backtest \
  -c configs/backtest.yaml \
  --factor-source combined \
  --factor-json data/results/factor_library.json \
  --walk-forward
```

Document that each fold selects factors from `[selection_start, selection_end]`, applies `selection_lag_days`, and evaluates only `[forward_start, forward_end]`.

- [ ] **Step 6: Run tests**

Run: `.venv/bin/pytest tests/test_walk_forward.py tests/test_factor_selection.py tests/test_factor_metrics.py -q`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add configs/backtest.yaml quantaalpha/backtest/run_backtest.py quantaalpha/backtest/README.md quantaalpha/backtest/walk_forward.py tests/test_walk_forward.py
git commit -m "feat: expose walk-forward backtest mode"
```

---

### Task 7: End-To-End Smoke Test

**Files:**
- No new files required unless the smoke test reveals a defect.

- [ ] **Step 1: Run static tests**

Run: `.venv/bin/pytest tests/test_factor_metrics.py tests/test_factor_selection.py tests/test_walk_forward.py -q`

Expected: PASS.

- [ ] **Step 2: Run a small dry load**

Run:

```bash
python -m quantaalpha.backtest.run_backtest \
  -c configs/backtest.yaml \
  --factor-source alpha158_20 \
  --dry-run
```

Expected: prints factor load result and exits without training.

- [ ] **Step 3: Run a short walk-forward smoke backtest**

Use a temporary config with a short date range and `alpha158_20` to keep runtime bounded:

```bash
python -m quantaalpha.backtest.run_backtest \
  -c /tmp/quantaalpha_walk_forward_smoke.yaml \
  --factor-source alpha158_20 \
  --walk-forward
```

Expected:
- At least one fold runs.
- `walk_forward_summary.json` is saved under the configured output directory.
- Each fold output lists selected factors and forward-window metrics.
- No fold selects factors using dates after its decision date.

- [ ] **Step 4: Commit smoke-test fixes if needed**

```bash
git add quantaalpha/backtest tests configs/backtest.yaml
git commit -m "fix: stabilize walk-forward smoke backtest"
```

---

## Acceptance Criteria

- Static backtest behavior is unchanged unless `--walk-forward` or `walk_forward.enabled: true` is used.
- Walk-forward mode supports repeated folds such as `2015H1 -> 2015H2`, `2015H2 -> 2016H1`, and so on.
- Factor selection uses only the in-sample selection window after applying `selection_lag_days`.
- Each fold trains and validates inside the past selection window, then backtests only the forward window.
- Results include per-fold selected factors, per-fold metrics, and aggregate metrics.
- Unit tests cover fold generation, leakage-safe window boundaries, factor scoring, top-k selection, config loading, and runner wiring.
- A short smoke backtest runs successfully with `alpha158_20`.

## Future Extensions

- Add regime-aware factor selection after the base walk-forward path is stable.
- Add factor turnover constraints between adjacent folds.
- Add selection score options such as monthly IC win rate, missing-data penalty, correlation clustering, and transaction-cost-adjusted ranking.
- Add UI visualization for fold-level selected factors and rolling out-of-sample performance.
