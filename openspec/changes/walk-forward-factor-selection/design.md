## Context

`BacktestRunner` in `quantaalpha/backtest/runner.py` runs a single static backtest: load factors, compute custom factors, create a dataset from `dataset.segments`, train LightGBM, run Qlib portfolio backtest, and save one metrics file. Factor ranking uses stored full-context metrics rather than rolling in-sample windows, which introduces forward-looking bias.

`quantaalpha/backtest/factor_loader.py` already supports exact-expression deduplication, metric-based sorting, and `max_factors`. `quantaalpha/backtest/ic_metrics.py` computes daily cross-sectional Pearson IC and Rank IC between a factor and the forward-return label.

`configs/backtest.yaml` has fixed `data.start_time`, `data.end_time`, `dataset.segments`, and `backtest.backtest.start_time/end_time`.

## Goals / Non-Goals

**Goals:**
- Add an opt-in walk-forward backtest mode that eliminates forward-looking bias
- Select factors per-fold using only in-sample data respecting a configurable selection lag
- Keep existing static single-window backtest behavior unchanged
- Serialize per-fold results and aggregate metrics for analysis
- Reuse existing IC/ICIR computation infrastructure

**Non-Goals:**
- Market-regime-aware factor selection (left for future extension)
- Factor turnover constraints between adjacent folds
- UI visualization of fold-level results
- Real-time or streaming backtest execution

## Decisions

### 1. Orchestrator Pattern (separate class wrapping BacktestRunner)

**Decision**: `WalkForwardBacktestRunner` wraps a `BacktestRunner` instance rather than subclassing it.

**Alternatives considered**:
- *Subclass BacktestRunner*: Would tightly couple walk-forward logic to the base runner, making it hard to test in isolation and risking accidental breakage of the static path.
- *Rewrite from scratch*: Unnecessary duplication of factor loading, dataset building, and backtest execution.

**Rationale**: Composition lets the orchestrator call stable runner methods while keeping walk-forward state (folds, selection results) separate.

### 2. Precomputed Feature Frame

**Decision**: Build and cache one full feature DataFrame for all candidate factors once, then slice columns per fold.

**Alternatives considered**:
- *Reload Qlib factors per fold*: Repeated I/O and parsing for N folds at large scale — wasteful when the candidate set is constant.
- *Lazy loading with cache*: Adds complexity for marginal benefit; the candidate set is typically bounded.

**Rationale**: A single precomputed frame gives deterministic per-window selection and avoids redundant Qlib feature reloading.

### 3. Factor Scoring Metric

**Decision**: V1 scores factors by `abs(Rank_IC)` descending, then `abs(Rank_ICIR)` descending, then valid-day count descending.

**Alternatives considered**:
- *Sharpe ratio of IC*: Sensitive to outliers in short windows.
- *Correlation-based clustering*: Adds complexity without proven benefit for V1.

**Rationale**: Rank IC is robust to outliers and matches the existing factor-quality direction used in `factor_loader.py`. The scoring function is a pluggable callable, so alternatives can be swapped in later.

### 4. Selection Lag

**Decision**: Default `selection_lag_days = 2` with a configurable integer.

**Rationale**: The current label uses `Ref($close, -2) / Ref($close, -1) - 1`, which references future prices. Without a lag, factor selection at the decision boundary would peek into the forward window. Two days covers the label's forward reference and one extra buffer day.

### 5. Internal Validation Split

**Decision**: Split the selection window chronologically: last `internal_valid_ratio` fraction for validation, earlier portion for training.

**Alternatives considered**:
- *Random split*: Would mix future and past data within the selection window.
- *No validation split*: Qlib requires train/valid/test segments.

**Rationale**: Chronological split respects temporal ordering — a standard practice for time-series model evaluation.

### 6. CLI Integration

**Decision**: Single `--walk-forward` flag on the existing `run_backtest.py` script, plus YAML-based enablement via `walk_forward.enabled: true`.

**Alternatives considered**:
- *Separate entry point script*: Unnecessary — the config loading, factor source selection, and logging infrastructure are shared.
- *Only CLI or only config*: Providing both lets scripted pipelines use config while ad-hoc runs use the CLI flag.

## Risks / Trade-offs

- **Large feature frame memory**: With thousands of candidate factors and multi-year daily data, the precomputed frame could exhaust memory. Mitigation: Document the trade-off; future work can add chunked selection if needed.
- **Fold boundary edge cases**: Short date ranges or large `selection_lag_days` could make folds invalid. Mitigation: `generate_walk_forward_folds` raises clear `ValueError` on invalid configurations.
- **Fold-level model variance**: Each fold trains a separate LightGBM model; small fold windows may have higher variance. Mitigation: Configurable `selection_window_months` and `min_selection_days` let users tune for stability.
- **No hyperparameter tuning per fold**: Each fold uses the same model params from config. Mitigation: Document that hyperparameter optimization across folds is a future extension.

## Open Questions

- None. All design parameters have defaults derived from the existing label configuration and half-year fold cadence.
