# Design: Regime-Aware Factor Feedback

## Context

The system now has two new capabilities:

1. **Market regime detection** — classify market state (e.g., `calm_bull`, `volatile_bear`) from price data using `MarketRegimeDetector` and a pre-built monthly regime map (`data/regime/monthly_regime_map.csv`).
2. **Regime-aware factor selection** — label walk-forward folds with regime tags, filter folds by regime, aggregate performance by regime.

Currently, the factor mining loop (`AlphaAgentLoop`) evaluates factors using aggregate backtest metrics (IC, annualized return, IR, max drawdown) over the entire date range. The LLM feedback mechanism (`generate_feedback()`) has no awareness of how a factor performs under different market regimes. A factor might have great aggregate IC but only work in bull markets and fail in bear markets — and the LLM wouldn't know.

This design adds regime-aware performance data to the LLM feedback prompt, enabling the LLM to judge factor robustness across market environments.

## Goals / Non-Goals

**Goals:**
- Compute per-regime backtest metrics by slicing the backtest date range using the monthly regime map
- Present a regime side-by-side comparison table in the LLM feedback prompt
- Add descriptive guidance so the LLM knows how to interpret regime-specific results
- Keep the feature opt-in via config; zero impact when disabled
- Reuse the existing `filter_dates_by_regime()` utility and monthly regime map CSV

**Non-Goals:**
- Regime-targeted factor generation (Idea A — prompt hints during generation) — reserved for future
- Adding structured regime breakdown to `Experiment.result` (Approach 2) — reserved for future
- Changing factor scoring or selection logic
- Real-time regime detection during mining
- Modifying the hypothesis generation or factor construction prompts

## Decisions

### 1. Feedback-layer injection (Approach 1)

**Choice:** Modify only `process_results()` and the feedback template. The regime map is loaded at `AlphaAgentLoop` init and passed through to `generate_feedback()`. No changes to `FactorTask`, `Experiment`, `Scenario`, or the loop workflow.

**Alternatives considered:**
- Approach 2 (structured field on `Experiment.result`): Cleaner data model but touches more files; premature if feedback is the only consumer.
- Approach 3 (scenario-level regime context): Most comprehensive but couples scenario to regime data; overkill for evaluation-only scope.

**Rationale:** Minimal blast radius, easy to toggle, natural upgrade path to Approach 2 if needed.

### 2. Pre-built monthly regime map as the source

**Choice:** Use `data/regime/monthly_regime_map.csv` produced by `scripts/build_regime_map.py`. Slicing is done by time ranges — for each regime, collect the month time intervals and filter the backtest result to those date ranges.

**Alternatives considered:**
- Per-day regime computation: Would run `MarketRegimeDetector.detect()` on every feedback call, producing noisy daily labels. Monthly aggregation gives a cleaner, more legible signal for the LLM.

**Rationale:** The regime map already exists and is fast (CSV lookup). Monthly granularity is appropriate for the LLM's decision-making — it needs a clean interpretable signal, not daily precision.

### 3. Side-by-side table format

**Choice:** A single table with one column per regime, same metric rows as the existing result table, plus a trading-day count row per regime.

**Alternatives considered:**
- Stacked sections: Harder for the LLM to compare across regimes.
- Inline text summary: Loses quantitative detail the LLM needs for evaluation.

**Rationale:** Side-by-side comparison makes relative performance across regimes immediately visible. The trading-day count gives the LLM statistical context.

### 4. Config toggle under `regime` section

**Choice:** New `regime.regime_aware_feedback` boolean in the experiment YAML config. Passed through `AlphaAgentLoop` → summarizer.

Alternatives considered:
- Environment variable: Less discoverable, no per-run control.
- Always-on: Would break if regime map doesn't exist yet.

**Rationale:** Opt-in avoids surprising existing workflows. Config file is the natural place for experiment parameters.

## Architecture

### Data Flow

```
experiment.yaml                    monthly_regime_map.csv
      │                                      │
      ▼                                      │
AlphaAgentLoop.__init__()                     │
  reads regime_aware_feedback                 │
  loads regime map ───────────────────────────┘
      │
      ▼
AlphaAgentLoop.run()
  └─► feedback step
        └─► summarizer.generate_feedback(exp, hypothesis, trace)
              └─► process_results(current, sota, regime_map)
                    ├─► combined_result (overall table, unchanged)
                    └─► regime_table (new, None if disabled)
              └─► renders prompt template with both tables
```

### Computation

`process_results()` gains an optional `regime_map` parameter. When provided:

1. Use `filter_dates_by_regime(regime_map, regime_label, start, end)` for each observed regime label to get date slices.
2. Filter the backtest result to each regime's date ranges.
3. Compute the same 4 metrics per subset (IC, annualized return, IR, max drawdown).
4. Build a side-by-side DataFrame → string.

When `regime_map` is `None`, behavior is identical to current — single table returned, second return value is `None`.

### Prompt Template

The `factor_feedback_generation.user` template gains a conditional block:

```jinja2
{% if regime_table %}
**Regime-Aware Performance Analysis:**

The factor's performance has been broken down by market regime. Each regime represents a distinct market environment:
- `calm_bull`: low volatility + rising prices
- `calm_bear`: low volatility + falling prices
- `volatile_bull`: high volatility + rising prices
- `volatile_bear`: high volatility + falling prices

The table shows the same metrics computed over only the trading days belonging to each regime.

When interpreting:
- A factor that performs consistently across all regimes is more robust and generalizable
- A factor that performs well in only one regime is regime-dependent — it may fail when the market transitions
- Pay attention to the trading-day count per regime: a regime with very few days may have unreliable metrics
- If the factor shows strong performance in the regime matching current market conditions, that is a positive signal for short-term deployment

Regime breakdown:
{{ regime_table }}
{% endif %}
```

### Regime Table Format

```
metric          | calm_bull | calm_bear | volatile_bull | volatile_bear
IC              |    0.05   |   0.03    |     0.01      |     0.02
ann_return      |    0.12   |   0.04    |    -0.08      |     0.15
IR              |    0.80   |   0.30    |    -0.50      |     0.90
max_dd          |   -0.08   |  -0.12    |    -0.25      |    -0.10
n_trading_days  |     342   |    198    |      87       |      201
```

### Edge Cases

- **Result date range partially outside regime map**: Dates not covered are excluded from per-regime computation. Metrics are computed only on available dates.
- **Regime has < min_days (20) trading days**: The regime column is included but marked with an asterisk and a note: `*low sample (<20 days), metrics may be unreliable`.
- **Regime map file missing**: Log a warning, `regime_map` loads as `None`, feature is silently disabled.
- **Regime map covers no dates in the result range**: `regime_table` is `None`, the prompt template omits the section.

## Changes Summary

| File | Change |
|------|--------|
| `quantaalpha/factors/feedback.py` | `process_results()` gains optional `regime_map` param, returns `(str, str | None)` tuple. `generate_feedback()` receives regime map, passes to both `process_results()` and prompt template. |
| `quantaalpha/factors/prompts/prompts.yaml` | Add `{% if regime_table %}` guidance block to `factor_feedback_generation.user`. |
| `quantaalpha/pipeline/loop.py` | `AlphaAgentLoop.__init__()` reads `regime_aware_feedback` config, loads regime map from path, stores on `self`. |
| `quantaalpha/pipeline/factor_mining.py` | Pass `regime` config section through to `AlphaAgentLoop`. |
| `configs/experiment.yaml` (or equivalent) | Add `regime.regime_aware_feedback` and `regime.regime_map_path` fields with defaults. |

## Config Schema

```yaml
regime:
  regime_aware_feedback: false   # default: false (opt-in)
  regime_map_path: "data/regime/monthly_regime_map.csv"  # default
```

## Testing

- **Unit**: `process_results()` with a mock regime map → verifies correct per-regime metric computation and table format.
- **Unit**: `process_results()` with `regime_map=None` → returns `None` for regime_table, `combined_result` unchanged from current behavior.
- **Unit**: Regime map partially covering result date range → uncovered dates excluded, covered dates correctly grouped.
- **Unit**: Regime with < 20 trading days → `*low sample` annotation present.
- **Integration**: Full `generate_feedback()` call with regime enabled → output prompt contains `Regime-Aware Performance Analysis` section with correct table.
- **Integration**: Full `generate_feedback()` call with regime disabled → output prompt identical to pre-change behavior.

## Future: Upgrade to Approach 2

If regime feedback proves valuable, the upgrade path is:

1. Move regime breakdown computation earlier — compute after backtest execution, store as a structured field on `Experiment.result` (e.g., `result.regime_breakdown: dict[str, dict]`).
2. `generate_feedback()` reads from `exp.result.regime_breakdown` instead of computing inline.
3. The prompt template and table format remain unchanged — same string table, just sourced from structured data.

This makes regime breakdown available to all downstream consumers (hypothesis generation prompts, trajectory metrics, output files) without changing the LLM-facing presentation.
