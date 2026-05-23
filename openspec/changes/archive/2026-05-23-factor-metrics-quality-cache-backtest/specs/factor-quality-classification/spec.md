## ADDED Requirements

### Requirement: Classify factor quality from per-factor metrics
The system SHALL assign each factor a `quality` label of `high`, `medium`, `low`, or `unknown` based exclusively on its `factor_metrics` Rank IC.

#### Scenario: High quality factor
- **WHEN** a factor has `factor_metrics` with `abs(Rank_IC) >= 0.03` and `n_days >= 10`
- **THEN** the factor's `quality` SHALL be `high`

#### Scenario: Medium quality factor
- **WHEN** a factor has `factor_metrics` with `abs(Rank_IC) >= 0.01` and `n_days >= 10` but below the high threshold
- **THEN** the factor's `quality` SHALL be `medium`

#### Scenario: Low quality factor
- **WHEN** a factor has `factor_metrics` with `abs(Rank_IC) < 0.01` and `n_days >= 10`
- **THEN** the factor's `quality` SHALL be `low`

#### Scenario: Unknown quality factor
- **WHEN** a factor entry has no `factor_metrics` key, all metric values are null, or `n_days < 10`
- **THEN** the factor's `quality` SHALL be `unknown`

### Requirement: Quality must not use experiment-level metrics
The system SHALL NOT use `experiment_backtest_results` or `backtest_results` to classify factor quality.

#### Scenario: Factor with experiment metrics but no factor_metrics
- **WHEN** a factor has valid experiment backtest results (e.g., Sharpe > 1.0) but no `factor_metrics`
- **THEN** the factor's `quality` SHALL be `unknown`, not `high`
