## ADDED Requirements

### Requirement: WalkForwardConfig regime fields
`WalkForwardConfig` SHALL include three new optional fields: `regime_method: str = ""`, `regime_vol_window: int = 60`, `regime_n_regimes: int = 2`. An empty `regime_method` SHALL disable all regime logic with zero overhead.

#### Scenario: Regime disabled by default
- **WHEN** `regime_method` is `""` (default)
- **THEN** no regime detection runs, `FoldResult.regime` is `None`, and all outputs are identical to pre-change behavior

#### Scenario: Regime enabled
- **WHEN** `regime_method` is `"volatility_direction"`
- **THEN** the runner SHALL compute regime for each fold's selection window

### Requirement: FoldResult regime field
`FoldResult` SHALL include an optional `regime: str | None` field that stores the dominant regime label for the fold's selection window.

#### Scenario: Regime populated
- **WHEN** a fold's selection window regime is detected as `"volatile_bear"`
- **THEN** `FoldResult.regime` SHALL be `"volatile_bear"`

#### Scenario: Regime disabled
- **WHEN** `regime_method` is `""`
- **THEN** `FoldResult.regime` SHALL be `None`

### Requirement: Regime computed from selection window
The runner SHALL compute regime using the selection window's own price data via `MarketRegimeDetector.dominant_regime()`. Regime SHALL NOT use data outside the selection window.

#### Scenario: Selection window regime
- **WHEN** fold selection window is 2018-01-01 to 2018-06-30
- **THEN** regime SHALL be computed from price data within those dates only

### Requirement: Regime in fold output
`walk_forward_folds.json` SHALL include a `"regime"` field per fold entry.

#### Scenario: JSON output includes regime
- **WHEN** walk-forward results are saved
- **THEN** each fold object in `walk_forward_folds.json` SHALL contain `"regime": "volatile_bear"` (or `null` if disabled)

### Requirement: Regime in selected factors CSV
`walk_forward_selected_factors.csv` SHALL include a `regime` column alongside `fold_id` and `factor_name`.

#### Scenario: CSV output includes regime
- **WHEN** walk-forward results are saved
- **THEN** each row in `walk_forward_selected_factors.csv` SHALL have a `regime` column with the fold's regime label (or empty if disabled)

### Requirement: Regime summary output
The system SHALL produce `walk_forward_regime_summary.json` containing per-regime aggregated factor performance metrics including `n_folds`, `avg_mean_ic`, `avg_mean_rank_icir`, and `top_factors` list.

#### Scenario: Regime summary generated
- **WHEN** walk-forward completes with regime enabled
- **THEN** `walk_forward_regime_summary.json` SHALL exist with one entry per observed regime

#### Scenario: Regime summary skipped when disabled
- **WHEN** `regime_method` is `""`
- **THEN** `walk_forward_regime_summary.json` SHALL NOT be created

### Requirement: Factor selection logic unchanged
`select_top_factors()` SHALL remain unchanged. Regime does not affect IC computation or factor ranking. Regime is purely metadata for analysis and downstream filtering.

#### Scenario: IC computation independent of regime
- **WHEN** `select_top_factors()` is called with `regime_label=None`
- **THEN** factor scores SHALL be identical to pre-change behavior

### Requirement: Backward compatibility
All new config fields SHALL have defaults that preserve existing behavior. No existing output format SHALL break. Existing tests SHALL pass without modification.

#### Scenario: No config change
- **WHEN** a user runs walk-forward without adding any new config fields
- **THEN** all outputs SHALL be byte-identical to pre-change outputs (except regime fields defaulting to null)

### Requirement: Regime filter on WalkForwardConfig
`WalkForwardConfig` SHALL include an optional `regime_filter: str = ""` field. When non-empty, `WalkForwardBacktestRunner.run()` SHALL skip folds whose `dominant_regime()` does not match `regime_filter`. When empty (default), no filtering occurs.

#### Scenario: Regime filter skips non-matching folds
- **WHEN** `regime_filter` is `"volatile_bear"` and fold 2 is `"volatile_bear"` but fold 3 is `"calm_bull"`
- **THEN** fold 2 proceeds normally and fold 3 is skipped with a log message

#### Scenario: Regime filter empty means no filtering
- **WHEN** `regime_filter` is `""` (default)
- **THEN** all folds are processed regardless of regime

#### Scenario: No folds match the filter
- **WHEN** `regime_filter` is `"volatile_bear"` but no fold has that regime
- **THEN** a `ValueError` is raised with a message listing available regimes

### Requirement: CLI --regime flag
The `run_backtest.py` CLI SHALL accept a `--regime` flag that overrides `regime_filter` in the YAML config. The flag SHALL only take effect when `--walk-forward` is also specified.

#### Scenario: --regime flag filters folds
- **WHEN** `run_backtest.py` is called with `--walk-forward --regime volatile_bear`
- **THEN** only folds with regime `"volatile_bear"` are processed

#### Scenario: --regime without --walk-forward is ignored
- **WHEN** `run_backtest.py` is called with `--regime volatile_bear` but without `--walk-forward`
- **THEN** a warning is logged and the flag is ignored; the static backtest runs normally

### Requirement: Monthly regime map tool
The system SHALL provide `scripts/build_regime_map.py` to produce a reusable monthly regime classification CSV (`data/regime/monthly_regime_map.csv`) covering the configured benchmark and date range.

#### Scenario: Regime map covers full date range
- **WHEN** `build_regime_map.py` is run with default parameters
- **THEN** `data/regime/monthly_regime_map.csv` is created with columns `year, month, month_start, month_end, regime, n_trading_days`

#### Scenario: Regime map filtering utility
- **WHEN** `filter_dates_by_regime(regime_map, "volatile_bear", "2018-01-01", "2020-12-31")` is called
- **THEN** a DataFrame is returned containing only months matching the given regime and date range
