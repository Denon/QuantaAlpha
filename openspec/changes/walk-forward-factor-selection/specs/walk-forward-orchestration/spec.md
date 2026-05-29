## ADDED Requirements

### Requirement: Precompute feature frame once

The system SHALL load and concatenate all candidate factor features (Qlib factors, custom computed factors, external data) into a single precomputed DataFrame once, before fold iteration begins. Duplicate column names SHALL be dropped.

#### Scenario: Combined feature frame includes all sources

- **WHEN** the config specifies both Qlib factors (e.g., alpha158_20) and custom factor JSON files
- **THEN** the returned DataFrame contains columns from both sources with no duplicate names

#### Scenario: Purely custom factors produce a valid frame

- **WHEN** factor_source.type is "custom" and no Qlib expressions are loaded
- **THEN** the returned DataFrame contains only custom factor columns

#### Scenario: No factors available raises error

- **WHEN** no Qlib factors are loaded and no custom factors are specified
- **THEN** a ValueError is raised

### Requirement: Apply fold window to runner config

The system SHALL update the `BacktestRunner` config's `dataset.segments` and `backtest.backtest.start_time/end_time` to match a fold's train, valid, and test date ranges.

#### Scenario: Runner config reflects fold windows

- **WHEN** `_apply_backtest_window` is called with train=("2015-01-01","2015-05-15"), valid=("2015-05-16","2015-06-29"), test=("2015-07-01","2015-12-31")
- **THEN** `config["dataset"]["segments"]["train"]` is ["2015-01-01", "2015-05-15"] and `config["backtest"]["backtest"]["start_time"]` is "2015-07-01"

### Requirement: Run single-fold backtest from feature frame

The system SHALL create a Qlib dataset from a selected feature DataFrame (subset of columns from the precomputed frame) and run the standard train-and-backtest pipeline, producing a metrics dictionary.

#### Scenario: Feature frame with selected factors produces metrics

- **WHEN** `run_feature_frame` is called with a DataFrame containing two factor columns
- **THEN** a metrics dict is returned containing at minimum the backtest performance metrics

### Requirement: Orchestrate full walk-forward backtest

The system SHALL iterate through all folds, for each fold: deep-copy the runner config from the original baseline (so fold windows never leak between folds), select top-k factors from the in-sample selection window, apply fold-specific train/valid/test windows, run a backtest with only the selected factors, and collect results.

Per-fold output SHALL include the fold ID, date ranges, selected factor names, and backtest metrics. Aggregate metrics SHALL be computed as the mean of each numeric metric across all folds.

#### Scenario: Two-fold walk-forward produces two fold results with config isolation

- **WHEN** a walk-forward run produces 2 folds
- **THEN** the `WalkForwardResult.folds` list has length 2, each fold has a non-empty `selected_factors` list, and each fold's `runner.config` was restored from the original baseline before applying the fold's windows

#### Scenario: Aggregate metrics include mean of numeric fields

- **WHEN** fold 1 has annualized_return=0.10 and fold 2 has annualized_return=0.20
- **THEN** aggregate `mean_annualized_return` is 0.15

### Requirement: Serialize walk-forward results

The system SHALL save per-fold results as `walk_forward_folds.json`, selected factor names per fold as `walk_forward_selected_factors.csv`, and aggregate metrics as `walk_forward_summary.json` in the experiment's output directory.

#### Scenario: Output files exist after successful run

- **WHEN** a walk-forward run completes successfully
- **THEN** `walk_forward_folds.json`, `walk_forward_selected_factors.csv`, and `walk_forward_summary.json` are written to the output directory

### Requirement: CLI dispatch to walk-forward mode

The system SHALL accept a `--walk-forward` CLI flag on `run_backtest.py`. When the flag is present OR `walk_forward.enabled` is true in the YAML config, the system SHALL dispatch to `WalkForwardBacktestRunner` instead of the default static backtest path.

Before dispatching to the walk-forward orchestrator, the system SHALL apply all CLI overrides (`--factor-source`, `--factor-json`, `--experiment`) to the runner config, identical to how they are applied in the static backtest path.

#### Scenario: --walk-forward flag triggers walk-forward mode with CLI overrides applied

- **WHEN** `run_backtest.py` is called with `--walk-forward --factor-source combined --factor-json data/results/factor_library.json`
- **THEN** the walk-forward orchestrator is invoked and `runner.config["factor_source"]["type"]` is overridden to "combined" before execution begins

#### Scenario: --walk-forward flag triggers walk-forward mode

- **WHEN** `run_backtest.py` is called with `--walk-forward`
- **THEN** the walk-forward orchestrator is invoked instead of `runner.run()`

#### Scenario: Static backtest when walk-forward is not enabled

- **WHEN** neither `--walk-forward` nor `walk_forward.enabled: true` is set
- **THEN** the existing static backtest path executes unchanged
