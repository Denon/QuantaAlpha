## ADDED Requirements

### Requirement: Compute per-factor daily cross-sectional IC
The system SHALL compute, for each factor, the daily cross-sectional Information Coefficient (IC) and Rank IC between the factor values and the aligned forward-return label, grouped by (datetime, instrument) alignment.

#### Scenario: Two factors produce different IC against the same label
- **WHEN** two factors are computed for the same universe and date range with the same forward-return label
- **THEN** each factor's `factor_metrics` contains independent IC, ICIR, Rank IC, Rank ICIR, n_days, and n_obs values that may differ

#### Scenario: Factor with no aligned observations
- **WHEN** a factor has fewer than 10 cross-sections with at least 3 overlapping instruments between factor and label
- **THEN** the system SHALL record `n_days` as the actual count but classify quality as `unknown`

### Requirement: Store per-factor metrics in factor library
The system SHALL persist per-factor IC metrics under a `factor_metrics` key in each factor library entry, containing: `IC` (mean daily Pearson IC), `ICIR` (IC / std(IC)), `Rank_IC` (mean daily Spearman rank IC), `Rank_ICIR` (Rank_IC / std(Rank_IC)), `n_days` (number of valid cross-sections), and `n_obs` (total observations).

#### Scenario: Library entry serialization with factor_metrics
- **WHEN** a factor library experiment with two factors is saved
- **THEN** each factor entry contains its own `factor_metrics` dict with the six fields above
- **AND** the experiment-level `experiment_backtest_results` is shared across all factors in the experiment

#### Scenario: Legacy library entry without factor_metrics
- **WHEN** a library entry is loaded that has `backtest_results` but no `factor_metrics`
- **THEN** the entry SHALL load successfully with `quality` defaulting to `unknown`
