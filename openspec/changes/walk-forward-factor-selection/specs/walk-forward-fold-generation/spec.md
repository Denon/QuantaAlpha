## ADDED Requirements

### Requirement: Generate walk-forward folds from config

The system SHALL generate a list of non-overlapping walk-forward folds from a `WalkForwardConfig`. Each fold SHALL include a selection window, decision date, forward window, and internal train/validation split.

The selection window end date SHALL be `decision_date - selection_lag_days`. The forward window start SHALL equal the decision date. The internal validation split SHALL be the last `internal_valid_ratio` fraction of the selection window.

#### Scenario: Half-year folds over two years

- **WHEN** config has start_time="2015-01-01", end_time="2016-12-31", selection_window_months=6, forward_window_months=6, step_months=6, selection_lag_days=2
- **THEN** exactly 3 folds are generated with fold IDs 1, 2, 3

#### Scenario: Fold boundaries respect selection lag

- **WHEN** decision date is 2015-07-01 and selection_lag_days=2
- **THEN** selection_end is 2015-06-29 (2 days before decision date)

#### Scenario: Fold forward window capped at global end time

- **WHEN** global end_time is earlier than decision_date + forward_window_months
- **THEN** forward_end equals the global end_time

#### Scenario: No valid selection window raises error

- **WHEN** selection_lag_days exceeds the selection window length
- **THEN** a ValueError is raised

### Requirement: Config loading with data-range defaults

The system SHALL load `WalkForwardConfig` from the raw YAML config, using `data.start_time` and `data.end_time` as defaults when `walk_forward.start_time` or `walk_forward.end_time` are not set. All numeric fields SHALL have sensible defaults as specified in the config schema.

#### Scenario: Walk-forward times fall back to data range

- **WHEN** `walk_forward` block has enabled=true and top_k=5 but no start_time/end_time
- **THEN** start_time and end_time are read from `data.start_time` and `data.end_time`

#### Scenario: Walk-forward disabled by default

- **WHEN** `walk_forward.enabled` is absent or false
- **THEN** `WalkForwardConfig.enabled` is False
