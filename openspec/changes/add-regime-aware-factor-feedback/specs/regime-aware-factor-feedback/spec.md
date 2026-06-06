## ADDED Requirements

### Requirement: Config toggle for regime-aware feedback
The system SHALL support an optional `regime` section in the experiment YAML config with fields `regime_aware_feedback: bool` (default `false`) and `regime_map_path: str` (default `"data/regime/monthly_regime_map.csv"`). When `regime_aware_feedback` is `false`, the feature SHALL be disabled with zero behavioral change.

#### Scenario: Feature disabled by default
- **WHEN** `regime_aware_feedback` is `false` (or absent from config)
- **THEN** `process_results()` SHALL NOT receive a regime map, and the feedback prompt SHALL NOT contain any regime analysis section

#### Scenario: Feature enabled
- **WHEN** `regime_aware_feedback` is `true` and a valid `regime_map_path` file exists
- **THEN** `AlphaAgentLoop` SHALL load the regime map at init and pass it to `generate_feedback()` on every feedback iteration

#### Scenario: Feature enabled but map file missing
- **WHEN** `regime_aware_feedback` is `true` but `regime_map_path` does not exist
- **THEN** the system SHALL log a warning and disable the feature (regime map loads as `None`)

### Requirement: Per-regime metric computation
`process_results()` SHALL accept an optional `regime_map` parameter (default `None`). When a regime map is provided, the function SHALL compute the same four metrics (IC, annualized return, information ratio, max drawdown) separately for each regime present in the map. For each regime, the function SHALL take the union of all month intervals belonging to that regime label, filter the backtest result to those dates (chronologically sorted), and compute metrics on the resulting subset. Metrics SHALL be computed as follows on each regime's date subset:
- **IC**: Pearson correlation between predicted and actual returns across all dates in the subset (cross-sectional, no temporal ordering required)
- **Annualized return**: Compound all daily returns within the subset, then annualize: `(∏(1 + r))^(252/n) - 1`
- **Information ratio**: Annualized return divided by annualized standard deviation of daily returns on the subset
- **Max drawdown**: Peak-to-trough drawdown on the chronologically-sorted daily return series, treating non-contiguous intervals as a stitched equity curve (i.e., drawdown is computed as if those dates were the only trading days)

#### Scenario: Per-regime metrics from multiple non-contiguous intervals
- **WHEN** `process_results()` is called with a regime map where `calm_bull` has three non-contiguous monthly intervals (Jan 2018, Apr 2018, Jul 2018) and the backtest result spans Jan–Dec 2018
- **THEN** the function SHALL union all three intervals into a single `calm_bull` date mask, filter the result to those dates ordered chronologically, and compute a single set of aggregate metrics (IC, annualized return, IR, max drawdown) from that combined subset

#### Scenario: Per-regime metrics computed
- **WHEN** `process_results()` is called with a regime map containing `calm_bull` and `volatile_bear` regimes, and the backtest result spans 500 trading days
- **THEN** the function SHALL return a `combined_result` string (overall metrics) AND a `regime_table` string containing a side-by-side table with IC, annualized return, IR, max drawdown, and n_trading_days per regime

#### Scenario: No regime map provided
- **WHEN** `process_results()` is called without a regime map (default `None`)
- **THEN** the function SHALL return only the `combined_result` string and `None` for the second value; behavior SHALL be identical to pre-change

#### Scenario: Backtest dates outside regime map range
- **WHEN** the backtest result contains dates not covered by the regime map
- **THEN** uncovered dates SHALL be excluded from per-regime metric computation; only covered dates contribute to regime-specific metrics

#### Scenario: Low sample regime
- **WHEN** a regime has fewer than 20 trading days of backtest data
- **THEN** the regime column SHALL be annotated with `*low sample` and the interpretive guidance SHALL note that metrics for that regime may be unreliable

#### Scenario: Regime map covers no backtest dates
- **WHEN** the regime map date range does not overlap the backtest result dates at all
- **THEN** `regime_table` SHALL be `None` and no regime section SHALL appear in the prompt

### Requirement: Regime performance table format
The regime table SHALL present each regime as a column with metric names as rows, using a side-by-side Markdown table format. The table SHALL include a `n_trading_days` row indicating the number of trading days used to compute each regime's metrics.

#### Scenario: Table structure
- **WHEN** the regime table is generated for regimes `calm_bull` and `volatile_bear`
- **THEN** the table SHALL have columns `metric`, `calm_bull`, `volatile_bear` and rows for IC, annualized return, IR, max drawdown, and n_trading_days

### Requirement: Regime-aware feedback prompt
When a `regime_table` is available, the feedback prompt template SHALL append a `Regime-Aware Performance Analysis` section containing interpretive guidance about regime labels, how to weigh regime-specific performance, and the side-by-side regime table.

#### Scenario: Regime section in prompt
- **WHEN** `generate_feedback()` renders the feedback prompt with a non-None `regime_table`
- **THEN** the prompt SHALL contain:
  - A descriptive block explaining the four regime labels (`calm_bull`, `calm_bear`, `volatile_bull`, `volatile_bear`)
  - Guidance on interpreting regime-consistent vs regime-dependent performance
  - A note about low-sample regimes
  - The side-by-side regime metrics table

#### Scenario: No regime section when disabled
- **WHEN** `generate_feedback()` renders the feedback prompt with `regime_table` as `None`
- **THEN** the prompt SHALL NOT contain any regime analysis section and SHALL be identical to pre-change behavior

### Requirement: Extraction of regime utilities for import
The system SHALL make `load_regime_map()` and `filter_dates_by_regime()` importable from `scripts.build_regime_map` for use by the feedback module. These functions SHALL be importable without triggering side effects or CLI execution.

#### Scenario: Safe import
- **WHEN** a module executes `from scripts.build_regime_map import load_regime_map, filter_dates_by_regime`
- **THEN** no CLI execution or side effects SHALL occur; only the functions SHALL be loaded
