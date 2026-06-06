## Context

The factor mining loop (`AlphaAgentLoop`) iterates through propose → exp_gen → coding → running → feedback. In the feedback step, `generate_feedback()` calls `process_results()` to build a comparison table from the backtest result, then renders a Jinja2 template with the hypothesis, factor details, and combined results. The LLM evaluates whether the factor supports the hypothesis and suggests improvements.

The system now has `data/regime/monthly_regime_map.csv` (produced by `scripts/build_regime_map.py`) with columns `year, month, month_start, month_end, regime, n_trading_days`. The `filter_dates_by_regime()` utility can slice this map to get date ranges for a specific regime.

The change enriches `process_results()` to compute per-regime metrics by slicing the backtest result into regime-specific date subsets, then rendering a side-by-side comparison table that is inserted into the feedback prompt.

## Goals / Non-Goals

**Goals:**
- Add per-regime performance breakdown to the feedback prompt without changing the mining loop flow
- Keep the feature opt-in via config flag; zero behavioral change when disabled
- Reuse existing regime map CSV and `filter_dates_by_regime()` utility
- Maintain backward compatibility — existing callers of `process_results()` are unaffected

**Non-Goals:**
- Regime-targeted factor generation (prompt hints during hypothesis generation)
- Structured regime breakdown on `Experiment.result` (Approach 2 upgrade)
- Modifying factor scoring, selection logic, or the hypothesis/factor-construction prompts
- Per-day regime detection during mining

## Decisions

### 1. `process_results()` gains regime_map parameter; returns tuple

**Choice:** `process_results(current_result, sota_result, regime_map=None) -> (str, str | None)`. When `regime_map` is `None`, the second return value is `None` — existing callers see no change. When provided, it returns `(combined_result_str, regime_table_str)`.

**Alternatives considered:**
- Separate `build_regime_table()` function: Cleaner separation but adds a new function the caller must orchestrate. The regime slicing needs the same `current_result` DataFrame; co-locating avoids passing state twice.
- Inline in `generate_feedback()`: Would bypass `process_results()` but the feedback method already calls `process_results()` — better to keep result formatting in one place.

**Rationale:** `process_results()` is the single chokepoint for result table formatting. Extending its return is the smallest change that doesn't require callers to know about regime internals.

### 2. Regime map loaded at AlphaAgentLoop init

**Choice:** `AlphaAgentLoop.__init__()` reads the `regime_aware_feedback` config flag and loads the regime map once via `load_regime_map(path)`. The map is stored on `self` and passed to `generate_feedback()` on each iteration.

**Alternatives considered:**
- Load in `generate_feedback()` each call: Simpler to wire but re-reads CSV on every feedback iteration (up to 100+ times per mining run).
- Module-level lazy cache: Hidden state, harder to test, less explicit.

**Rationale:** Load once, reuse across all feedback iterations. Explicit passing makes the dependency visible and testable.

### 3. Slicing by time ranges, not per-day labeling

**Choice:** For each regime label in the map (e.g., `calm_bull`), call `filter_dates_by_regime(regime_map, label, start, end)` to get month time intervals. Filter the backtest result to those intervals. Compute metrics on the filtered subset.

**Alternatives considered:**
- Per-day label join: Slower (row-by-row merge), conceptually treats each day as independent when regime periods are contiguous.

**Rationale:** Time-range slicing respects the contiguous nature of regime periods, is computationally cheaper, and directly uses the existing `filter_dates_by_regime()` API.

### 4. Side-by-side table in prompt template

**Choice:** A single Markdown table with one column per regime, identical metric rows to the existing result table, plus `n_trading_days`. Wrapped in a Jinja2 `{% if regime_table %}` block with interpretive guidance.

**Alternatives considered:**
- Stacked per-regime sections: Harder for LLM to compare across regimes at a glance.
- Natural language summary: Strips quantitative detail the LLM needs.

**Rationale:** Side-by-side format lets the LLM immediately see performance differences across regimes. The guidance text teaches the LLM how to weigh regime-specific results.

### 5. Utility imports from scripts/

**Choice:** Import `load_regime_map` and `filter_dates_by_regime` from `scripts.build_regime_map`. The file is a script but contains importable functions with no side effects on import.

**Alternatives considered:**
- Move to `quantaalpha/backtest/regime_map.py`: Cleaner module location but widens scope beyond what this change requires.
- Inline the logic: Duplicates existing code.

**Rationale:** Direct import is the simplest path. If reuse grows, extraction to a proper module can be done later without changing callers.

## Risks / Trade-offs

- **Regime map stale or missing** → Feature silently degrades (map loads as `None`); logged warning. User must run `build_regime_map.py` to refresh.
- **Regime map date range doesn't cover backtest dates** → Per-regime metrics only computed for covered dates. Regime columns may have very different `n_trading_days` counts. LLM guidance includes this consideration.
- **Template size increase** → Regime table adds ~200-300 tokens to each feedback prompt. Acceptable given context windows; the insight gained outweighs the cost.
- **Import from scripts/ directory** → `scripts/build_regime_map.py` was written as a CLI tool, not a library module. If it gains import-time side effects in the future, this could break. Mitigated by its current implementation (pure function definitions + `if __name__ == "__main__"` guard).
