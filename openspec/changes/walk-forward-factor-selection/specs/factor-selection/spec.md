## ADDED Requirements

### Requirement: Score a single factor within a date window

The system SHALL compute factor quality metrics (Rank IC, Rank ICIR, IC, ICIR, n_days, n_obs) for a single factor series within a specified date window, using the cross-sectional IC metrics infrastructure in `ic_metrics.py`.

A factor with fewer than `min_days` valid days in the window SHALL NOT receive a score and SHALL be reported as rejected with reason "insufficient_valid_days".

#### Scenario: Factor scored on window with sufficient data

- **WHEN** a factor has 50 valid trading days in the selection window and min_days=10
- **THEN** a `FactorScore` is returned with rank_ic, rank_icir, ic, icir, n_days, and n_obs fields

#### Scenario: Factor rejected for insufficient days

- **WHEN** a factor has only 5 valid trading days in the selection window and min_days=10
- **THEN** None is returned from the scoring function

### Requirement: Select top-k factors by quality

The system SHALL score all candidate factors within the specified window, rank them by `abs(Rank_IC)` descending, then `abs(Rank_ICIR)` descending, then `n_days` descending, then factor name alphabetically, and return the top-k.

If `top_k` is 0, all scored factors SHALL be included. Rejected factors SHALL be reported with a reason string.

#### Scenario: Top-2 selection from three factors

- **WHEN** three factors are scored with distinct rank IC values and top_k=2
- **THEN** the two factors with the highest absolute rank IC are selected

#### Scenario: All factors selected when top_k is zero

- **WHEN** top_k=0 and three factors all pass min_days
- **THEN** all three factors are in the selected list

#### Scenario: Empty factor causes rejection

- **WHEN** a factor contains only NaN values in the selection window
- **THEN** it appears in the rejected dict with reason "insufficient_valid_days"

### Requirement: Window slicing respects date boundaries

The system SHALL restrict factor scoring to rows whose `datetime` index level falls between `selection_start` and `selection_end` inclusive.

#### Scenario: Data outside window is excluded

- **WHEN** the factor DataFrame contains rows from 2024-01-01 to 2024-12-31 and the selection window is 2024-01-01 to 2024-01-31
- **THEN** only rows within January 2024 contribute to the IC metrics
