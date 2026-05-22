## ADDED Requirements

### Requirement: Deduplicate identical factor expressions
The system SHALL remove duplicate factor expressions before computation, keeping only the first occurrence.

#### Scenario: Two identical expressions in factor list
- **WHEN** the factor list contains `"close / delay(close, 1) - 1"` twice
- **THEN** only one instance SHALL proceed to computation and backtest

#### Scenario: Expressions differ only in whitespace
- **WHEN** the factor list contains `"close / delay(close,1)-1"` and `"close / delay(close, 1) - 1"`
- **THEN** both SHALL be treated as separate expressions (whitespace is not normalized)

### Requirement: Sort factors by metric priority
The system SHALL sort factors by `abs(Rank_IC)` descending, then `abs(ICIR)` descending, then creation time ascending, before applying the cap.

#### Scenario: Factors with different Rank IC values
- **WHEN** three factors have Rank IC values of -0.05, 0.02, and 0.04
- **THEN** they SHALL sort in order: abs(-0.05)=0.05, abs(0.04)=0.04, abs(0.02)=0.02

#### Scenario: Factors with no factor_metrics in sort
- **WHEN** a factor has `quality: unknown` (no `factor_metrics`)
- **THEN** it SHALL sort after all factors with metrics, using creation time as tiebreaker

### Requirement: Configurable max_factors cap
The system SHALL limit the number of factors passed to backtest computation to a configurable `max_factors` value, defaulting to 50.

#### Scenario: Default cap applied
- **WHEN** 80 factors are selected and no `max_factors` override is configured
- **THEN** only the top 50 factors (by sort order) SHALL be computed and backtested

#### Scenario: Config override raises cap
- **WHEN** `max_factors` is set to 100 in configuration
- **THEN** up to 100 factors SHALL be computed and backtested

#### Scenario: Config override removes cap
- **WHEN** `max_factors` is set to 0 or null in configuration
- **THEN** all factors SHALL be computed and backtested
