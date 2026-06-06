## Context

The backend already computes per-regime IC performance during factor mining via `build_regime_table()` in `quantaalpha/factors/feedback.py`. This produces a Markdown table for the LLM feedback prompt but discards the structured data afterward. The factor library JSON stores `factor_metrics` (aggregate IC statistics) but has no per-regime breakdown. The frontend Factor Library page shows aggregate IC metrics on cards and in the detail modal but has no awareness of market regime performance.

## Goals / Non-Goals

**Goals:**
- Extend `build_regime_table()` to return structured per-regime metrics alongside the Markdown table
- Persist per-regime metrics and a computed summary into the factor library JSON during mining
- Display compact best/worst regime summary on factor cards
- Display full per-regime metrics table in the factor detail modal
- Add a "Best Regime" filter dropdown and aggregate stats card to the Factor Library page
- Provide a backfill script for existing factors

**Non-Goals:**
- Regime display on the Mining Dashboard page
- On-demand regime computation at page load time
- Regime data in WebSocket streaming metrics
- New API endpoints

## Decisions

### 1. Extend `build_regime_table()` return type (not a new function)

**Choice:** Change return type from `str | None` to `tuple[str | None, dict | None]`. The dict maps `factor_name -> {regime: metrics}`. Also compute `regime_summary` (best_regime, worst_regime, regime_stability) per factor.

**Alternatives considered:**
- New standalone function: Would duplicate the Qlib loading, label computation, and date-regime mapping logic. Unnecessary when `build_regime_table()` already traverses all the data.
- Modify `build_regime_table()` to only return structured data and move Markdown rendering to the caller: Larger refactor, higher risk of breaking LLM feedback.

**Rationale:** Minimal change to existing working code. The Markdown table is preserved for the LLM; the structured dict is a new output for persistence.

### 2. Pre-compute and store in factor library JSON (not on-demand)

**Choice:** Persist `regime_metrics` and `regime_summary` during mining into the factor library JSON. API serves as-is with no changes.

**Rationale:** The data is already computed during mining — the only gap is persistence. On-demand computation would require re-evaluating factor expressions against Qlib data, adding latency and complexity for no benefit.

### 3. `regime_stability` formula

**Choice:** `1 - std(Rank_IC_across_regimes) / mean(|Rank_IC|_across_regimes)`, clamped to [0, 1].

**Alternatives considered:**
- Range-based: `(max - min) / mean` — more sensitive to outliers.
- Variance-based without normalization: Not comparable across factors with different IC scales.

**Rationale:** Coefficient-of-variation-based formula normalizes by the factor's own IC magnitude, making stability comparable across factors.

### 4. Two-tier display (compact card + full modal)

**Choice:** Factor cards show a single-line best/worst regime summary. The detail modal shows the full per-regime metrics table.

**Rationale:** Users browse many factors on one page — compact cards prevent information overload. The detail modal provides complete information when a factor looks interesting.

### 5. Regime filter as dropdown (not clickable stats card)

**Choice:** Add a `<select>` dropdown in the filter bar next to quality buttons. Composes with quality filter using AND logic.

**Rationale:** Extensible pattern for future filters. Clear combinational behavior with existing filter.

## Risks / Trade-offs

- **Regime data staleness**: If the regime map is rebuilt with different parameters, existing factors' `regime_metrics` won't update. → Mitigation: Run backfill script after regime map rebuild.
- **Factor library JSON size**: Each factor gains ~500 bytes of regime data. For libraries with hundreds of factors, this could be noticeable. → Mitigation: Negligible compared to existing `factor_metrics` and `backtest_results` fields (~2KB each).
- **Only new factors get regime data**: Factors mined before this change won't have regime data until backfill. → Mitigation: UI gracefully hides regime info when absent.
