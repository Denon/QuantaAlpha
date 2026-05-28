## ADDED Requirements

### Requirement: Build Qlib dataset from aligned DataFrames

The system SHALL accept a features DataFrame and a labels DataFrame, both with `(datetime, instrument)` MultiIndex, and produce a Qlib `DatasetH` with the specified train/valid/test segments.

The builder SHALL accept both `(datetime, instrument)` and `(instrument, datetime)` index orders, normalizing to `(datetime, instrument)`.

#### Scenario: DatasetH contains feature and label columns

- **WHEN** features has columns ["factor_a", "factor_b"] and label has column "LABEL0"
- **THEN** the resulting DatasetH `feature` col_set returns columns ["factor_a", "factor_b"]

#### Scenario: Index normalized from instrument-first to datetime-first

- **WHEN** the input DataFrame has index levels ["instrument", "datetime"]
- **THEN** the builder reorders to ["datetime", "instrument"] before constructing the dataset

### Requirement: Handle missing and infinite values

The system SHALL fill NaN values with 0 and clip infinite values in the feature DataFrame before performing cross-sectional rank normalization. Rows where the label is NaN SHALL be dropped from both features and labels.

#### Scenario: NaN features filled with zero

- **WHEN** a feature column contains NaN values
- **THEN** those values are replaced with 0 before normalization

#### Scenario: Rows without labels are dropped

- **WHEN** a label value is NaN for a given (datetime, instrument)
- **THEN** that row is excluded from the feature DataFrame and label DataFrame in the dataset

### Requirement: Cross-sectional rank normalization

The system SHALL apply cross-sectional rank normalization to features: within each date, each feature's values SHALL be rank-transformed and scaled to [0, 1].

#### Scenario: Rank normalization produces bounded values

- **WHEN** a feature column has values [10, 20, 30, 40] on a single date
- **THEN** after normalization the values are in [0, 1] and preserve the original rank order
