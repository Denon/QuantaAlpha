## ADDED Requirements

### Requirement: External columns injected into factor computation DataFrame
The system SHALL inject external data columns with `$` prefix into the DataFrame returned by `get_qlib_stock_data()`, making them available for expression-based factor evaluation.

#### Scenario: External market_cap column available in expression
- **WHEN** external data contains a `market_cap` column AND config specifies the file
- **THEN** `get_qlib_stock_data()` returns a DataFrame containing `$market_cap` alongside `$open, $close, $volume` etc.

#### Scenario: No external data configured
- **WHEN** config has no `external_data` section
- **THEN** `get_qlib_stock_data()` returns only the default Qlib fields, behavior unchanged

### Requirement: External columns merged as standalone features in backtest dataset
The system SHALL merge external data columns as feature columns in the backtest dataset so they participate in model training and backtest without requiring a wrapper expression.

#### Scenario: External data merged alongside computed factors
- **WHEN** both custom computed factors and external data exist
- **THEN** the dataset contains feature columns from both sources, deduplicated

#### Scenario: Only external data, no custom factors
- **WHEN** config has `factor_source.type: alpha158_20` AND external data is configured AND no custom factors are computed
- **THEN** the dataset contains both alpha158_20 factors AND external data columns

### Requirement: Per-factor IC metrics computed for external data
The system SHALL compute per-factor IC metrics (IC, Rank IC, ICIR, Rank ICIR) for each external data column using the same `compute_factor_metrics()` function used for expression-based factors.

#### Scenario: External data IC metrics in output
- **WHEN** external data is loaded with 3 columns
- **THEN** `per_factor_metrics` in the run output contains entries for all 3 columns with IC, Rank IC, etc.

### Requirement: Duplicate handling between external and computed columns
When an external data column has the same name as a computed factor, the computed factor SHALL take precedence.

#### Scenario: Name collision
- **WHEN** external data has column `momentum_10d` AND a computed factor is also named `momentum_10d`
- **THEN** the computed factor value is kept and the external column is dropped with a logged warning
