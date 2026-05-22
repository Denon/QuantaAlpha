## Context

The QuantaAlpha factor library stores computed factors alongside experiment backtest results. Currently, experiment-level metrics (Sharpe, returns, max drawdown from the combined model) are displayed on individual factor cards as if they represent that factor's standalone quality. The backtest cache uses a simple MD5 hash of the expression string, ignoring market universe, date range, and data provider — so switching from CSI 300 to CSI 500 silently returns cached results from the wrong universe.

This change introduces true per-factor IC metrics computed cross-sectionally against the forward-return label, makes factor quality depend on those metrics alone, scopes the cache to prevent cross-universe contamination, and adds factor selection controls to keep backtest runtime predictable.

## Goals / Non-Goals

**Goals:**
- Compute and persist per-factor IC/ICIR/Rank IC/Rank ICIR in the factor library
- Classify factor quality (`high`/`medium`/`low`/`unknown`) strictly from per-factor metrics
- Separate experiment-level backtest results from per-factor metrics in storage and UI
- Prevent backtest cache from serving results across different markets, date ranges, or providers
- Cap backtest factor count at a configurable limit with deduplication and metric-based priority sorting

**Non-Goals:**
- Full single-factor portfolio backtests (e.g., long-short returns per factor)
- Changing the combined model backtest logic itself
- Purging or migrating existing cache files beyond rejection-on-read
- Real-time factor computation or streaming metrics

## Decisions

### 1. Cross-sectional daily IC as the per-factor metric

**Choice**: Compute IC/Rank IC daily (cross-sectionally across instruments), then aggregate to mean IC, std(IC), ICIR = mean/std, plus Rank IC variants.

**Why**: Cross-sectional IC is the standard quant finance measure of a factor's predictive power. It isolates the factor's signal from the model's combination logic. Alternative considered: time-series IC per instrument — rejected because it confounds factor quality with instrument-specific drift.

### 2. Rank IC thresholds for quality classification

**Choice**: `high` if |Rank IC| >= 0.03, `medium` if >= 0.01, `low` if below, `unknown` if no metrics. Require minimum valid days (10) to avoid classifying noise.

**Why**: Rank IC is robust to outliers and non-normality. The 0.03/0.01 thresholds are standard in industry. Alternative: IC (Pearson) thresholds — rejected because Pearson IC is sensitive to distribution shape.

### 3. Cache key scoping via tuple hash

**Choice**: MD5 hash of `(expression, market, date_start, date_end, provider_uri)` instead of just expression.

**Why**: A factor computed for CSI 300 over 2020-2022 with provider A is not valid for CSI 500 over 2023-2024 with provider B. Alternative: cache per directory per market — rejected because it doesn't prevent date range mismatches.

### 4. Instrument validation on cache read

**Choice**: Load cached H5/legacy file, extract instrument set, compare against configured market's instrument set; reject if mismatch.

**Why**: Even scoped keys can collide if the user changes the market definition without changing the name. This is a defense-in-depth check. The cost is one extra file read on cache hit.

### 5. Dedup then sort by abs(Rank IC), cap at max_factors

**Choice**: Deduplicate expressions first (keeping the first occurrence), sort by `abs(Rank IC)` desc then `abs(ICIR)` desc then creation time, take top N. Default N=50, overridable in config.

**Why**: Duplicate expressions waste computation and bias the model. Sorting by absolute Rank IC maximizes the expected signal in the capped set. Alternative: random sampling — rejected because it's non-deterministic.

### 6. Legacy backward compatibility

**Choice**: Old library entries without `factor_metrics` load as `quality: unknown`. `backtest_results` remains readable but is never written by new code; new code writes `experiment_backtest_results`.

**Why**: No need to force regeneration of old libraries. Users can re-run to populate `factor_metrics` and get quality labels.

## Risks / Trade-offs

- **Existing factor cards change their displayed metrics**: Users who relied on experiment Sharpe being shown on factor cards will see IC-based metrics instead → Show experiment metrics in detail view only; document the change.
- **Backtest recomputation on first run after deploy**: Scoped cache keys mean all cached results are stale on first run → Accept the one-time recomputation cost.
- **max_factors=50 may drop factors users care about**: The cap prioritizes by Rank IC, which aligns with quality but may exclude niche factors → Make it configurable so users can raise or remove it.
- **IC computation depends on label alignment**: If the label definition changes, old `factor_metrics` are silently stale → Cache key scoping includes date range; regenerating the library for a new label is the expected workflow.

## Migration Plan

1. Deploy code changes: new fields in library schema, new cache key format, new UI
2. Existing libraries load with `quality: unknown` on factor cards
3. Existing caches are rejected on read (instrument mismatch or key mismatch); recomputation runs
4. Users re-run factor library generation to populate `factor_metrics` and `quality`
5. New cache files are written with scoped keys

No database migration needed — the factor library is file-based (JSON/Parquet).

## Open Questions

- Should we expose the per-factor IC time series (daily IC values) in the UI, or only the aggregates? → Start with aggregates only; add time series if users request it.
- Should `max_factors` be a hard cap or a warning? → Hard cap by default, configurable to unlimited.
