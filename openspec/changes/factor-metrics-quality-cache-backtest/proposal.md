## Why

The current factor library conflates experiment-level backtest metrics (combined model performance) with per-factor quality signals. Factor cards display experiment-wide Sharpe/returns as if they were per-factor metrics, quality labels are derived from the wrong data, and the backtest cache silently reuses results across incompatible markets and date ranges. This makes the factor library misleading for factor selection and the backtest pipeline unreliable.

## What Changes

- **Per-factor IC metrics**: Compute IC, ICIR, Rank IC, Rank ICIR cross-sectionally per factor against the aligned forward-return label. Store under `factor_metrics` in the factor library. These are the source of truth for factor quality.
- **Factor quality classification**: Add `quality: high | medium | low | unknown` derived exclusively from `factor_metrics` (Rank IC thresholds: >= 0.03 high, >= 0.01 medium). Entries without `factor_metrics` default to `unknown`.
- **Separate experiment metrics**: Rename combined model backtest results to `experiment_backtest_results`. Keep `backtest_results` for backward compatibility but stop consuming it in factor cards, quality labels, and ranking.
- **Scoped backtest caching**: MD5 cache keys now include expression + market + date range + provider URI + label expression. Validate cached instruments against the configured market (reject on mismatch). Legacy unscoped cache files are ignored; new scoped files are written alongside them.
- **Backtest feature selection**: Deduplicate identical expressions, sort by abs(Rank IC) then abs(ICIR), apply configurable `max_factors` (default 50) before computation.
- **Frontend updates**: Factor cards read `factor_metrics` and `quality`; experiment metrics shown only in detail view as "experiment/model metrics."

## Capabilities

### New Capabilities

- `per-factor-ic-metrics`: Compute cross-sectional daily IC/ICIR/Rank IC/Rank ICIR per factor, aligned on (datetime, instrument) with the label, and store results in the factor library.
- `factor-quality-classification`: Classify each factor as high/medium/low/unknown using only per-factor Rank IC thresholds.
- `backtest-cache-scoping`: Scope backtest cache keys by expression, market, date range, and provider URI; validate cached instruments before reuse.
- `backtest-feature-selection`: Deduplicate, sort by metric, and cap factor count before backtest computation.

### Modified Capabilities

None — no existing spec files to modify.

## Impact

- **`quantaalpha/factors/library.py`**: New fields `factor_metrics`, `quality`, `experiment_backtest_results`; read compatibility for legacy entries.
- **`quantaalpha/backtest/`**: New per-factor IC helper, updated factor loader with selection logic, cache key scoping.
- **`frontend-v2/backend/app.py`**: API responses use `factor_metrics` and `quality`; experiment metrics moved to detail view.
- **Frontend factor cards/components**: Type definitions and display logic updated for new field schema.
- **Cache files**: New scoped key format; legacy unscoped cache files rejected on first run, with new scoped files written alongside them.
