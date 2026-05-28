## Why

The current backtesting framework runs a single static backtest where factor selection uses stored full-context metrics computed over the entire dataset. This introduces forward-looking bias — factors are selected based on data that wouldn't be known at decision time. Walk-forward factor selection eliminates this leakage by scoring factors using only in-sample windows and evaluating the selected set on the next out-of-sample period, producing realistic out-of-sample performance estimates.

## What Changes

- New `walk_forward.py` module with config, fold generation, and orchestrator classes
- New `factor_selection.py` module for window-aware factor scoring and top-k selection using IC/ICIR metrics
- New `precomputed_dataset.py` module extracting reusable dataset builder from the current inline implementation in `runner.py`
- **New** `WalkForwardBacktestRunner` class that orchestrates multiple folds, each with its own factor selection and backtest execution
- Modified `BacktestRunner` with new helper methods for prepared feature frames and fold-level window configuration
- Modified `run_backtest.py` with `--walk-forward` CLI flag and dispatch logic
- Modified `configs/backtest.yaml` with a disabled-by-default `walk_forward` configuration block
- Updated `quantaalpha/backtest/README.md` with walk-forward usage documentation
- New unit tests for fold generation, factor scoring, dataset building, and orchestration
- **Explicitly non-breaking**: static backtest path is unchanged when walk-forward is not enabled

## Capabilities

### New Capabilities

- `walk-forward-fold-generation`: Generate chronological, non-overlapping folds from config with selection-lag-aware boundaries and internal train/validation splits
- `factor-selection`: Score candidate factors within a specified date window using cross-sectional IC/ICIR metrics and select top-k factors
- `walk-forward-orchestration`: Orchestrate full walk-forward backtests by precomputing features, selecting factors per-fold, running single-window backtests, and aggregating results
- `precomputed-dataset`: Build Qlib DatasetH from pre-aligned feature/label DataFrames with cross-sectional rank normalization

### Modified Capabilities

None — all existing backtest capabilities are preserved unchanged.

## Impact

- **Code**: New files in `quantaalpha/backtest/` (walk_forward.py, factor_selection.py, precomputed_dataset.py). Modifications to runner.py (extract dataset builder + add helpers), run_backtest.py (CLI dispatch), and configs/backtest.yaml (new config block).
- **APIs**: No external API changes. Internal: `BacktestRunner` gains `prepare_feature_frame()`, `_apply_backtest_window()`, `_create_dataset_from_feature_frame()`, `run_feature_frame()` methods.
- **Dependencies**: No new dependencies. Uses existing pandas, numpy, Qlib, PyYAML stack.
- **Data**: New output files — `walk_forward_folds.json`, `walk_forward_selected_factors.csv`, `walk_forward_summary.json` per walk-forward run.
