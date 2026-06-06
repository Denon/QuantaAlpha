# Design: Frontend Display of Per-Regime Factor Performance

## Context

The backend already computes per-regime IC performance during factor mining via `build_regime_table()` in `quantaalpha/factors/feedback.py`. This produces a Markdown table showing per-regime IC, annual return, IR, and max drawdown — but only for the LLM feedback prompt. The data is never persisted to the factor library JSON, never served by the API, and never shown on the frontend.

This design adds per-regime performance metrics to the Factor Library page so users can evaluate factor robustness across market environments when browsing and selecting factors for further mining.

## Goals / Non-Goals

**Goals:**
- Persist per-regime IC metrics computed by `build_regime_table()` into the factor library JSON during mining
- Display per-regime breakdown on factor cards (compact: best/worst regime) and in the detail modal (full metrics table)
- Add a "Best Regime" filter dropdown to the Factor Library page
- Add an aggregate stats card showing factor distribution across regimes
- Provide a backfill script for existing factors

**Non-Goals:**
- Regime display on the Mining Dashboard page (future work)
- Real-time regime computation on factor page load (pre-computed only)
- Adding regime data to the WebSocket streaming metrics
- New API endpoints (existing `/api/v1/factors` is sufficient)

## Decisions

### 1. Pre-compute and store (not on-demand)

**Choice:** Extend `build_regime_table()` to return a structured dict alongside the Markdown table, then persist that dict into the factor library JSON during mining. The API serves it as-is. New factors get regime data automatically; existing factors get it via backfill.

**Alternatives considered:**
- On-demand computation: Would require re-evaluating factor expressions against Qlib data at page load time. Slow, brittle, and duplicates infrastructure.
- Standalone regime analysis service: Unnecessary complexity for what is essentially a data persistence problem.

**Rationale:** The data is already computed during mining — the only gap is that it's thrown away after the LLM prompt is rendered. Persisting it is the smallest possible change.

### 2. Two-tier display (compact cards + full detail modal)

**Choice:** Factor cards show a single-line best/worst regime summary. The detail modal shows a full per-regime metrics table with Rank IC, IC, ICIR, hit rate, and sample days for each regime.

**Rationale:** Users browse many factors on the page — compact cards prevent information overload. When a factor looks interesting, the detail modal provides the full picture needed for decision-making.

### 3. Filter dropdown for regime (not clickable stats card)

**Choice:** Add a `<select>` dropdown in the filter bar (next to quality filter buttons) for filtering by best regime. The aggregate stats card is display-only.

**Rationale:** User anticipates more filters in the future — a dropdown pattern is extensible. Composability with existing quality filter (AND logic) is natural with a dropdown.

## Design

### Data Model

New fields added to each factor entry in the factor library JSON:

```json
{
  "factor_id": "abc123",
  "regime_metrics": {
    "calm_bull": {
      "IC": 0.042, "ICIR": 0.85, "Rank_IC": 0.045,
      "hit_rate": 0.72, "n_days": 342, "n_months": 18
    },
    "volatile_bull": {
      "IC": 0.028, "ICIR": 0.61, "Rank_IC": 0.031,
      "hit_rate": 0.65, "n_days": 285, "n_months": 14
    },
    "calm_bear": {
      "IC": 0.015, "ICIR": 0.38, "Rank_IC": 0.018,
      "hit_rate": 0.58, "n_days": 164, "n_months": 9
    },
    "volatile_bear": {
      "IC": 0.007, "ICIR": 0.15, "Rank_IC": 0.009,
      "hit_rate": 0.48, "n_days": 98, "n_months": 5
    }
  },
  "regime_summary": {
    "best_regime": "calm_bull",
    "worst_regime": "volatile_bear",
    "regime_stability": 0.62
  }
}
```

New TypeScript interfaces in `frontend-v2/src/types/index.ts`:

```typescript
export interface RegimeMetrics {
  IC: number;
  ICIR: number;
  Rank_IC: number;
  hit_rate: number;
  n_days: number;
  n_months: number;
}

export interface RegimeSummary {
  best_regime: string;
  worst_regime: string;
  regime_stability: number;
}

// Added to Factor interface:
export interface Factor {
  // ... existing fields ...
  regimeMetrics?: Record<string, RegimeMetrics>;
  regimeSummary?: RegimeSummary;
}
```

`regime_stability` is defined as: `1 - (std_dev of per-regime Rank IC values) / (mean of absolute per-regime Rank IC values)`, clamped to [0, 1]. Higher = more consistent across regimes.

### Backend Changes

#### 1. `build_regime_table()` returns structured data

File: `quantaalpha/factors/feedback.py`

Change return type from `str | None` to `tuple[str | None, dict | None]`. The dict maps `factor_name -> {regime: {IC, ICIR, Rank_IC, hit_rate, n_days, n_months}}`. The existing Markdown table for the LLM prompt is preserved as the first element.

Additionally, compute `regime_summary` per factor: `best_regime`, `worst_regime` (by Rank IC), and `regime_stability`.

#### 2. Persist to factor library JSON

In the mining pipeline (caller of `build_regime_table()`), after receiving the structured dict, write `regime_metrics` and `regime_summary` into each factor's entry in the factor library JSON.

#### 3. API — no changes needed

The `/api/v1/factors` endpoint already passes through all fields from the factor library JSON (`app.py` lines 616-641). Once `regime_metrics` and `regime_summary` are in the JSON, they flow to the frontend automatically. The `FactorLibraryPage` already maps all API fields into the `Factor` type — the new fields just need to be added to the mapping.

#### 4. Backfill script

New script: `scripts/backfill_regime_metrics.py`

- Loads the factor library JSON
- For each factor, evaluates its expression against the regime map using `build_regime_table()` logic (or a simplified version that takes a single factor expression)
- Writes `regime_metrics` and `regime_summary` back to the JSON

### Frontend Changes

All changes are in `frontend-v2/src/pages/FactorLibraryPage.tsx` and `frontend-v2/src/types/index.ts`.

#### Factor Card (compact regime summary)

Below the existing IC metrics grid, add a single-line best/worst summary:

```
🏠 最佳环境: calm_bull (0.042) | 🔻 最差: volatile_bear (0.009)
```

Only shown when `factor.regimeSummary` exists.

#### Detail Modal (full regime table)

Add a new section between the per-factor IC metrics and the metadata section. Title: "不同市场环境表现" with a color-coded table:

| 市场环境 | Rank IC | IC | ICIR | 胜率 | 样本天数 |
|---------|--------|----|------|------|---------|
| calm_bull | 0.042 | 0.038 | 0.85 | 72% | 342 |
| volatile_bull | 0.031 | 0.028 | 0.61 | 65% | 285 |
| calm_bear | 0.018 | 0.015 | 0.38 | 58% | 164 |
| volatile_bear | 0.009 | 0.007 | 0.15 | 48% | 98 |

Rows are color-coded: green (strong), yellow, orange, red (weak). The stability score is shown as a badge in the section header.

#### Aggregate Stats Card

Add a 5th card to the stats row showing "最佳环境分布" — for each regime, the count of factors that perform best there:

```
🏠 最佳环境分布
calm_bull        22
volatile_bull    15
calm_bear         8
volatile_bear     5
```

The "best regime" for each factor is taken from `factor.regimeSummary.best_regime`. Factors without regime data are excluded from the count.

#### Regime Filter Dropdown

In the filter bar, after the quality filter buttons, add a divider and a `<select>` dropdown:

```
全部环境 | calm_bull (22) | volatile_bull (15) | calm_bear (8) | volatile_bear (5)
```

Selecting a regime filters the factor list to only those whose `regimeSummary.best_regime` matches. Composes with the quality filter using AND logic. Factors without regime data are hidden when a regime filter is active.

### Data Flow

```
Mining (feedback.py)
  build_regime_table()
    → (markdown_table, structured_regime_dict)
    → persist structured_regime_dict to factor library JSON

Frontend (FactorLibraryPage.tsx)
  GET /api/v1/factors
    → response includes regime_metrics, regime_summary
    → map to Factor type
    → render cards, stats, filters, modal
```

### Error Handling

- Factors without `regime_metrics` (pre-existing or computation failure): hide regime info gracefully — no regime row on card, no regime section in modal, excluded from aggregate stats and filter
- `build_regime_table()` failures: log warning, return `None` for structured dict, mining continues without regime data
- Backfill script: skip factors whose expressions can't be evaluated, report counts at end

### Testing

- Unit test: `build_regime_table()` returns properly shaped dict
- Unit test: `regime_stability` computation edge cases (single regime, all equal)
- Integration test: API response includes `regime_metrics` and `regime_summary` when present in JSON
- Manual: verify Factor Library page renders cards, modal, filter, and stats card correctly

## Implementation Order

1. Extend `build_regime_table()` to return structured dict + compute `regime_summary`
2. Persist regime metrics to factor library JSON during mining
3. Add TypeScript types (`RegimeMetrics`, `RegimeSummary`) and update `Factor` interface
4. Update API response mapping in `FactorLibraryPage` to pass through new fields
5. Update factor cards with single-line regime summary
6. Update detail modal with full regime metrics table
7. Add aggregate stats card ("最佳环境分布")
8. Add regime filter dropdown
9. Write backfill script (`scripts/backfill_regime_metrics.py`)
