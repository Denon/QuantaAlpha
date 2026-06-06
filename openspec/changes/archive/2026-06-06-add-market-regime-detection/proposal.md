## Why

Walk-forward factor selection currently evaluates factors purely on IC/ICIR without considering market context. This leads to poor out-of-sample performance (mean annualized return -22.5%, Rank ICIR 0.0 in prior runs). Factor performance has continuity within similar market environments — factors effective in bear markets tend to persist as long as the bear regime continues. Adding regime awareness enables selecting factors that are appropriate for the current market state.

## What Changes

- New `regime.py` module with pluggable strategy interface for market regime detection
- Default implementation: volatility bucketing + direction (bull/bear) →二维 regime labels
- `WalkForwardConfig` gains 4 new optional fields: `regime_method`, `regime_vol_window`, `regime_n_regimes`, `regime_filter`
- `FoldResult` gains `regime` field (string label per fold)
- New output file `walk_forward_regime_summary.json` with per-regime factor performance aggregation
- `walk_forward_selected_factors.csv` gains `regime` column
- `walk_forward_folds.json` includes `regime` field per fold
- `--regime` CLI flag to filter walk-forward backtest to only folds matching a specific regime
- `build_regime_map.py` tool to produce reusable monthly regime classification CSV

## Capabilities

### New Capabilities
- `market-regime-detection`: Regime detection logic — given a price series, produce a regime label (volatility + direction). Includes pluggable `RegimeStrategy` protocol and default `VolatilityDirectionStrategy`.
- `regime-aware-factor-selection`: Integration of regime labels into the walk-forward fold lifecycle — regime computation, fold labeling, and regime-based result aggregation.

### Modified Capabilities
<!-- No existing specs to modify -->

## Impact

- `quantaalpha/backtest/regime.py` — new module
- `quantaalpha/backtest/walk_forward.py` — `WalkForwardConfig`, `FoldResult`, `WalkForwardBacktestRunner.run()`, `_save_result()`, `_aggregate_metrics()`
- `tests/test_regime.py` — new test file
- `tests/test_walk_forward.py` — updated integration tests
- Output format changes: `walk_forward_folds.json`, `walk_forward_selected_factors.csv`, new `walk_forward_regime_summary.json`
