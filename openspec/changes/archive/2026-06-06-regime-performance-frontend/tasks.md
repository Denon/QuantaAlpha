## 1. Backend — Extend build_regime_table()

- [x] 1.1 Modify `build_regime_table()` return type from `str | None` to `tuple[str | None, dict | None]`, computing per-regime IC, ICIR, hit_rate, n_days, and n_months for each factor
- [x] 1.2 Compute `regime_summary` per factor (best_regime, worst_regime by Rank IC, regime_stability) in the caller after receiving structured data
- [x] 1.3 Add unit test verifying the structured dict shape and regime_stability computation

## 2. Backend — Persist regime metrics to factor library JSON

- [x] 2.1 Identify the caller of `build_regime_table()` in the mining pipeline and persist `regime_metrics` and `regime_summary` into the factor library JSON for each factor
- [x] 2.2 Handle failure cases: if `build_regime_table()` returns None, skip persistence without crashing the mining run
- [x] 2.3 Verify end-to-end: run a mining experiment, confirm newly generated factors in the JSON have `regime_metrics` and `regime_summary` fields

## 3. Backend — Backfill script

- [x] 3.1 Create `scripts/backfill_regime_metrics.py` that loads an existing factor library JSON, computes per-regime metrics for each factor expression using the regime map, and writes back
- [x] 3.2 Report counts: total processed, successfully updated, skipped, failed
- [x] 3.3 Test on the current factor library to ensure it doesn't corrupt existing data

## 4. Frontend — TypeScript types

- [x] 4.1 Add `RegimeMetrics` and `RegimeSummary` interfaces to `frontend-v2/src/types/index.ts`
- [x] 4.2 Add `regimeMetrics?: Record<string, RegimeMetrics>` and `regimeSummary?: RegimeSummary` to the `Factor` interface
- [x] 4.3 Update the API response mapping in `FactorLibraryPage.tsx` to pass through `regimeMetrics` and `regimeSummary` from API data

## 5. Frontend — Factor cards and detail modal

- [x] 5.1 Add compact best/worst regime summary line below the IC metrics grid on each factor card (only when `regimeSummary` exists)
- [x] 5.2 Add "不同市场环境表现" section to the detail modal with a color-coded per-regime metrics table (Rank IC, IC, ICIR, hit rate, sample days)
- [x] 5.3 Show regime stability badge in the section header

## 6. Frontend — Aggregate stats and filter

- [x] 6.1 Add "最佳环境分布" stats card showing factor count per best regime
- [x] 6.2 Add regime filter `<select>` dropdown after quality filter buttons with AND composability
- [x] 6.3 Ensure factors without regime data are gracefully hidden from regime-filtered views

## 7. Validation

- [x] 7.1 Verify API response: curl `/api/v1/factors` after mining and confirm `regimeMetrics` and `regimeSummary` are present
- [x] 7.2 Manual smoke test: open Factor Library page, verify cards show regime summary, modal shows table, filter works, stats card shows counts
