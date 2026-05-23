## 1. Per-Factor IC Metrics Computation

- [x] 1.1 Create reusable per-factor IC helper in `quantaalpha/backtest/ic_metrics.py` that computes daily cross-sectional Pearson IC and Rank IC between a factor series and the aligned forward-return label. Schema: IC, IC_std, ICIR, Rank_IC, Rank_IC_std, Rank_ICIR, n_days, n_obs.
- [x] 1.2 Implement daily aggregation: mean IC, IC_std, ICIR (mean/std), mean Rank IC, Rank_IC_std, Rank_ICIR, n_days, n_obs
- [x] 1.3 Store metric context (provider_uri, market, start_time, end_time, label_expr) alongside factor_metrics for staleness detection
- [x] 1.4 Handle edge cases: fewer than 2 instruments per cross-section, fewer than 10 valid days, missing label data

## 2. Factor Library Schema Updates

- [x] 2.1 Add `factor_metrics` and `quality` fields to factor entry serialization in `quantaalpha/factors/library.py`
- [x] 2.2 Rename experiment-level results to `experiment_backtest_results`; keep `backtest_results` read-only for legacy entries
- [x] 2.3 Implement `quality` classification from `factor_metrics` using Rank IC thresholds (high: >= 0.03, medium: >= 0.01, low: below, unknown: missing)
- [x] 2.4 Ensure legacy entries without `factor_metrics` load with `quality: unknown`

## 3. Backtest Cache Scoping

- [x] 3.1 Update cache key generation to hash `(expression, market, date_start, date_end, provider_uri, label_expr)` instead of expression alone
- [x] 3.2 Add instrument validation on cache read: compare cached instruments against configured market, reject if < 80% overlap
- [x] 3.3 Ensure recomputed factors are written with scoped cache keys
- [x] 3.4 Keep dashboard backtest recomputation enabled (do not pass `--skip-uncached` by default)

## 4. Backtest Feature Selection

- [x] 4.1 Implement exact expression deduplication in `quantaalpha/backtest/factor_loader.py` (keep first occurrence)
- [x] 4.2 Implement factor sorting: `abs(Rank_IC)` desc, then `abs(ICIR)` desc, then creation time asc; factors without metrics sort last
- [x] 4.3 Add configurable `max_factors` cap (default 50) to factor loader; support 0/null for unlimited
- [x] 4.4 Wire selection and cap into the backtest pipeline before custom factor computation
- [x] 4.5 Update config defaults (backtest.yaml or equivalent) to expose `max_factors` with default 50, and wire to the factor loader

## 5. Frontend API and UI Updates

- [x] 5.1 Update backend API responses in `frontend-v2/backend/app.py` to serve `factor_metrics` and `quality` on factor cards
- [x] 5.2 Move experiment-level metrics (`experiment_backtest_results`) to detail view only, labeled as "experiment/model metrics"
- [x] 5.3 Update frontend factor card types and components to display per-factor IC metrics and quality labels
- [x] 5.4 Add metric scope indicator on factor cards (e.g., "per-factor IC" vs "experiment backtest")

## 6. Testing

- [x] 6.1 Unit test per-factor IC calculation: two factors produce different IC/Rank IC against same label
- [x] 6.2 Unit test library serialization: two factors share `experiment_backtest_results` but have distinct `factor_metrics` and `quality`
- [x] 6.3 Unit test API conversion: factor card fields use `factor_metrics`; legacy entries return `quality: unknown`
- [x] 6.4 Unit test loader selection: duplicate expressions collapse, sort order correct, `max_factors` cap respected
- [x] 6.5 Unit test cache behavior: old cache rejected for different market; scoped key changes with market/date/provider
- [x] 6.6 Smoke test: rejected caches trigger recomputation, logs show computed factors, dataset alignment has nonzero rows

