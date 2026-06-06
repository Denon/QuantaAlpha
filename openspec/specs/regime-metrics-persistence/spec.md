## ADDED Requirements

### Requirement: build_regime_table() returns structured per-regime metrics

`build_regime_table()` in `quantaalpha/factors/feedback.py` SHALL return a tuple of `(markdown_table: str | None, regime_metrics_dict: dict | None)` instead of `str | None`. The dict SHALL map `factor_name -> {regime_label: {IC, ICIR, Rank_IC, hit_rate, n_days, n_months}}` for each factor workspace in the experiment. The Markdown table (first element) SHALL be unchanged for backward compatibility with the LLM feedback prompt.

#### Scenario: Successful computation returns both outputs
- **WHEN** `build_regime_table()` is called with a valid experiment and regime map, and per-regime IC is successfully computed
- **THEN** the first element is a non-empty Markdown string and the second element is a dict mapping factor names to per-regime metrics dicts

#### Scenario: Missing regime map returns None
- **WHEN** `build_regime_table()` is called with `regime_map=None`
- **THEN** it returns `(None, None)`

#### Scenario: No workspace files returns None
- **WHEN** `build_regime_table()` is called with an experiment that has no result.h5 files in its sub_workspace_list
- **THEN** it returns `(None, None)` and logs a warning

#### Scenario: Per-regime metrics include all required fields
- **WHEN** IC computation succeeds for a regime
- **THEN** the dict for that regime contains keys: `IC`, `ICIR`, `Rank_IC`, `hit_rate`, `n_days`, `n_months`

### Requirement: regime_summary computed per factor

For each factor in the structured dict, the caller SHALL compute a `regime_summary` containing `best_regime` (regime with highest absolute Rank IC), `worst_regime` (regime with lowest absolute Rank IC), and `regime_stability` (a float in [0, 1] where 1 = highly consistent).

#### Scenario: regime_stability is high when IC is similar across regimes
- **WHEN** a factor has Rank IC values [0.040, 0.042, 0.038, 0.041] across 4 regimes
- **THEN** `regime_stability` is greater than 0.9

#### Scenario: regime_stability is low when IC varies widely
- **WHEN** a factor has Rank IC values [0.045, 0.030, 0.010, 0.005] across 4 regimes
- **THEN** `regime_stability` is less than 0.4

#### Scenario: Single regime yields maximum stability
- **WHEN** a factor has data for only one regime
- **THEN** `regime_stability` is 1.0

### Requirement: Regime metrics persisted to factor library JSON

During factor mining, after `build_regime_table()` returns structured data, the mining pipeline SHALL write `regime_metrics` and `regime_summary` fields into each factor's entry in the factor library JSON file. The fields SHALL be written at the same time as `factor_metrics` and other per-factor data.

#### Scenario: Newly mined factor has regime data in JSON
- **WHEN** a mining experiment completes and a factor is saved to the factor library
- **THEN** the factor's JSON entry contains `regime_metrics` mapping regime labels to metric objects, and `regime_summary` containing `best_regime`, `worst_regime`, and `regime_stability`

#### Scenario: Regime computation failure skips persistence gracefully
- **WHEN** `build_regime_table()` returns `(None, None)` due to a computation failure
- **THEN** factors are still saved to the library without `regime_metrics` or `regime_summary` fields, and the mining run continues normally

### Requirement: Backfill script for existing factors

A script at `scripts/backfill_regime_metrics.py` SHALL compute and write `regime_metrics` and `regime_summary` for all factors in an existing factor library JSON. It SHALL use the same computation logic as the mining pipeline.

#### Scenario: Backfill adds regime data to existing factors
- **WHEN** the backfill script is run against a factor library JSON with factors that have expressions but no `regime_metrics`
- **THEN** each factor gains `regime_metrics` and `regime_summary` fields, and the total count of updated factors is reported

#### Scenario: Backfill skips factors that can't be evaluated
- **WHEN** a factor's expression cannot be evaluated (e.g., missing data, parse error)
- **THEN** that factor is skipped, a warning is logged, and processing continues with the next factor
