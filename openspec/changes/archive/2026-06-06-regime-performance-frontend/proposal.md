## Why

The backend already computes per-regime IC performance during factor mining (via `build_regime_table()`) and uses it to inform LLM feedback, but this data is discarded after the prompt is rendered. Users cannot see how factors perform across market environments when browsing the factor library, making it difficult to assess factor robustness or select candidates for further mining.

## What Changes

- Extend `build_regime_table()` to return structured per-regime metrics alongside the existing Markdown table
- Persist per-regime IC, ICIR, hit rate, and sample size into the factor library JSON during mining
- Display a compact best/worst regime summary on factor cards in the Factor Library page
- Show a full per-regime metrics table (Rank IC, IC, ICIR, hit rate, sample days) in the factor detail modal
- Add an aggregate "Best Regime Distribution" stats card to the Factor Library page
- Add a "Best Regime" filter dropdown to the filter bar, composable with the existing quality filter
- Provide a backfill script to compute regime metrics for existing factors in the library

## Capabilities

### New Capabilities

- `regime-metrics-persistence`: Persist per-regime factor performance metrics (IC, ICIR, Rank IC, hit rate, sample size) to the factor library JSON during mining, computed by `build_regime_table()`. Includes a `regime_summary` with best/worst regime and stability score.
- `regime-metrics-frontend-display`: Display per-regime factor performance on the Factor Library page — compact best/worst summary on factor cards, full per-regime metrics table in the detail modal, aggregate stats card showing factor distribution by best regime, and a regime filter dropdown.

### Modified Capabilities

<!-- No existing capabilities have spec-level requirement changes. Implementation details of regime-aware-factor-feedback change (return type of build_regime_table) but its requirement contract is unchanged. -->

## Impact

- **Python**: `quantaalpha/factors/feedback.py` — extend `build_regime_table()` return type; mining pipeline caller — persist regime data to JSON
- **Scripts**: New `scripts/backfill_regime_metrics.py`
- **Frontend**: `frontend-v2/src/types/index.ts` — new TypeScript interfaces; `frontend-v2/src/pages/FactorLibraryPage.tsx` — UI additions
- **Data**: Factor library JSON files gain `regime_metrics` and `regime_summary` fields per factor
- **API**: No changes — existing `/api/v1/factors` passes through new fields automatically
