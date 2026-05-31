## 1. Regime Detection Module

- [ ] 1.1 Create `quantaalpha/backtest/regime.py` with `RegimeStrategy` Protocol
- [ ] 1.2 Implement `VolatilityDirectionStrategy.detect()` — rolling volatility percentile bucketing + cumulative return direction
- [ ] 1.3 Implement `MarketRegimeDetector` facade with `detect()` and `dominant_regime()` methods
- [ ] 1.4 Write unit tests for `VolatilityDirectionStrategy` with synthetic price data (known patterns: monotonic decline → bear, monotonic increase → bull)
- [ ] 1.5 Write unit tests for `MarketRegimeDetector.dominant_regime()` — majority vote, tie-breaking, all-same-regime

## 2. Config Integration

- [ ] 2.1 Add `regime_method`, `regime_vol_window`, `regime_n_regimes` fields to `WalkForwardConfig` dataclass
- [ ] 2.2 Update `load_walk_forward_config()` to parse the 3 new fields from YAML dict
- [ ] 2.3 Write unit test: config loading with regime fields present
- [ ] 2.4 Write unit test: config loading without regime fields defaults to disabled

## 3. Runner Integration

- [ ] 3.1 Add `regime: str | None` field to `FoldResult` dataclass
- [ ] 3.2 In `WalkForwardBacktestRunner.run()`, compute market price series and detect regime per fold when `regime_method` is set
- [ ] 3.3 Pass regime label to `FoldResult` construction
- [ ] 3.4 Write integration test: `FoldResult.regime` populated when regime enabled
- [ ] 3.5 Write integration test: `FoldResult.regime` is `None` when regime disabled

## 4. Output Enhancements

- [ ] 4.1 Update `_save_result()` to include `regime` field in `walk_forward_folds.json`
- [ ] 4.2 Update `_save_result()` to include `regime` column in `walk_forward_selected_factors.csv`
- [ ] 4.3 Implement `_aggregate_regime_metrics()` to produce per-regime summary (n_folds, avg_mean_ic, avg_mean_rank_icir, top_factors)
- [ ] 4.4 Write `walk_forward_regime_summary.json` in `_save_result()` when regime enabled
- [ ] 4.5 Write unit test: regime summary JSON structure and content
- [ ] 4.6 Write unit test: regime summary not created when disabled

## 5. Backward Compatibility & Final Verification

- [ ] 5.1 Run existing tests in `tests/test_walk_forward.py` — all must pass unchanged
- [ ] 5.2 Run existing tests in `tests/test_factor_selection.py` — all must pass unchanged
- [ ] 5.3 Verify output format: existing walk-forward run without regime config produces identical outputs (except null regime fields)
- [ ] 5.4 Update `__init__.py` to export `MarketRegimeDetector` and `RegimeStrategy` if needed
