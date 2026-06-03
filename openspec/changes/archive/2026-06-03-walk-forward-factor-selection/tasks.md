## 1. Walk-Forward Config and Fold Generation

- [x] 1.1 Write failing tests for `generate_walk_forward_folds` with half-year windows, selection lag boundaries, and edge cases (tests/test_walk_forward.py)
- [x] 1.2 Implement `WalkForwardConfig`, `WalkForwardFold`, `generate_walk_forward_folds`, and `load_walk_forward_config` in `quantaalpha/backtest/walk_forward.py`
- [x] 1.3 Run fold generation tests and verify PASS
- [x] 1.4 Commit: `feat: add walk-forward fold generation and config loading`

## 2. Factor Selection Scoring

- [x] 2.1 Write failing tests for `select_top_factors` verifying window slicing, top-k ranking, and NaN rejection (tests/test_factor_selection.py)
- [x] 2.2 Implement `FactorScore`, `FactorSelectionResult`, `score_factor_window`, and `select_top_factors` in `quantaalpha/backtest/factor_selection.py` using abs(Rank_IC) > abs(Rank_ICIR) > n_days as sort key
- [x] 2.3 Run factor selection tests and verify PASS
- [x] 2.4 Commit: `feat: add rolling factor selection scoring`

## 3. Precomputed Dataset Builder

- [x] 3.1 Write failing test for `build_precomputed_dataset` verifying feature/label alignment and segment assignment (tests/test_walk_forward.py)
- [x] 3.2 Create `quantaalpha/backtest/precomputed_dataset.py` with index normalization, NaN/inf handling, cross-sectional rank normalization, and Qlib `DatasetH` construction
- [x] 3.3 Refactor `BacktestRunner._create_dataset_with_computed_factors` to delegate to `build_precomputed_dataset`
- [x] 3.4 Run dataset and metrics tests and verify PASS
- [x] 3.5 Commit: `refactor: extract precomputed dataset builder`

## 4. BacktestRunner Helpers for Feature Frames

- [x] 4.1 Write failing tests for `_apply_backtest_window` verifying segments and backtest range are updated (tests/test_walk_forward.py)
- [x] 4.2 Add `_apply_backtest_window`, `_create_dataset_from_feature_frame`, `run_feature_frame`, and `prepare_feature_frame` methods to `BacktestRunner`. Method `_apply_backtest_window` mutates `self.config` in place (the orchestrator is responsible for config isolation between folds, not this helper)
- [x] 4.3 Run runner tests and verify PASS
- [x] 4.4 Commit: `feat: add prepared feature frame backtest helpers`

## 5. WalkForwardBacktestRunner Orchestration

- [x] 5.1 Write failing test for full orchestration: mock runner, verify per-fold selection, fold-level backtest calls, and result aggregation (tests/test_walk_forward.py)
- [x] 5.2 Implement `FoldResult`, `WalkForwardResult`, `WalkForwardBacktestRunner` with `run()`, `_aggregate_metrics()`, and `_save_result()` in `walk_forward.py`. The orchestrator SHALL deep-copy the runner's original config before the fold loop and restore from the baseline before each fold's window is applied, ensuring config changes never leak between folds.
- [x] 5.3 Run orchestration tests and verify PASS
- [x] 5.4 Commit: `feat: add walk-forward backtest runner`

## 6. Config, CLI, and Documentation

- [x] 6.1 Add `walk_forward` block to `configs/backtest.yaml` with disabled-by-default and half-year defaults
- [x] 6.2 Add `--walk-forward` CLI flag to `run_backtest.py` and dispatch to `WalkForwardBacktestRunner` when enabled. Apply `--factor-source`, `--factor-json`, and `--experiment` overrides to the runner config identically to the static path before dispatching.
- [x] 6.3 Add wire tests for config loading with data-range fallbacks (tests/test_walk_forward.py)
- [x] 6.4 Document walk-forward usage in `quantaalpha/backtest/README.md` with example command and output file descriptions
- [x] 6.5 Run all backtest tests and verify PASS
- [x] 6.6 Commit: `feat: expose walk-forward backtest mode`

## 7. End-to-End Verification

- [x] 7.1 Run static backtest with `--dry-run` to confirm existing path is unchanged
- [x] 7.2 Run a short walk-forward smoke backtest with alpha158_20 and a bounded date range
- [x] 7.3 Verify output files exist (`walk_forward_folds.json`, `walk_forward_selected_factors.csv`, `walk_forward_summary.json`) and no factor selection uses data after `selection_end` (the actual leakage boundary, accounting for `selection_lag_days`)
- [x] 7.4 Fix any smoke-test issues and commit if needed: `fix: stabilize walk-forward smoke backtest`
