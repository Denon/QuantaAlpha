## 1. Regime Detection Module

- [x] 1.1 Create `quantaalpha/backtest/regime.py` with `RegimeStrategy` Protocol
- [x] 1.2 Implement `VolatilityDirectionStrategy.detect()` — rolling volatility percentile bucketing + cumulative return direction
- [x] 1.3 Implement `MarketRegimeDetector` facade with `detect()` and `dominant_regime()` methods
- [x] 1.4 Write unit tests for `VolatilityDirectionStrategy` with synthetic price data (known patterns: monotonic decline → bear, monotonic increase → bull)
- [x] 1.5 Write unit tests for `MarketRegimeDetector.dominant_regime()` — majority vote, tie-breaking, all-same-regime

## 2. Config Integration

- [x] 2.1 Add `regime_method`, `regime_vol_window`, `regime_n_regimes` fields to `WalkForwardConfig` dataclass
- [x] 2.2 Update `load_walk_forward_config()` to parse the 3 new fields from YAML dict
- [x] 2.3 Write unit test: config loading with regime fields present
- [x] 2.4 Write unit test: config loading without regime fields defaults to disabled

## 3. Runner Integration

- [x] 3.1 Add `regime: str | None` field to `FoldResult` dataclass
- [x] 3.2 In `WalkForwardBacktestRunner.run()`, compute market price series and detect regime per fold when `regime_method` is set
- [x] 3.3 Pass regime label to `FoldResult` construction
- [x] 3.4 Write integration test: `FoldResult.regime` populated when regime enabled
- [x] 3.5 Write integration test: `FoldResult.regime` is `None` when regime disabled

## 4. Output Enhancements

- [x] 4.1 Update `_save_result()` to include `regime` field in `walk_forward_folds.json`
- [x] 4.2 Update `_save_result()` to include `regime` column in `walk_forward_selected_factors.csv`
- [x] 4.3 Implement `_aggregate_regime_metrics()` to produce per-regime summary (n_folds, avg_mean_ic, avg_mean_rank_icir, top_factors)
- [x] 4.4 Write `walk_forward_regime_summary.json` in `_save_result()` when regime enabled
- [x] 4.5 Write unit test: regime summary JSON structure and content
- [x] 4.6 Write unit test: regime summary not created when disabled

## 5. Backward Compatibility & Final Verification

- [x] 5.1 Run existing tests in `tests/test_walk_forward.py` — all must pass unchanged
- [x] 5.2 Run existing tests in `tests/test_factor_selection.py` — all must pass unchanged
- [x] 5.3 Verify output format: existing walk-forward run without regime config produces identical outputs (except null regime fields)
- [x] 5.4 Update `__init__.py` to export `MarketRegimeDetector` and `RegimeStrategy` if needed

## 6. Regime Filtering

- [x] 6.1 Add `regime_filter: str = ""` field to `WalkForwardConfig` dataclass and `load_walk_forward_config()`
- [x] 6.2 In `WalkForwardBacktestRunner.run()`, skip folds whose regime doesn't match `regime_filter`; raise `ValueError` if no folds match
- [x] 6.3 Add `--regime` CLI flag to `run_backtest.py`, only active with `--walk-forward`
- [x] 6.4 Write unit tests: fold skipping when filter matches/doesn't match; all folds filtered raises ValueError
- [x] 6.5 Write unit test: `--regime` flag without `--walk-forward` logs warning
- [x] 6.6 Save `data/regime/monthly_regime_map.csv` as a committed asset; wire `build_regime_map.py` into the project
- [x] 6.7 Run existing tests — all must pass unchanged with new default field
