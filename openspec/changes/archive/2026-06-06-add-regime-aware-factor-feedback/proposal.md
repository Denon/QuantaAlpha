## Why

The factor mining loop currently evaluates factors using aggregate backtest metrics over the entire date range, with no awareness of market regime. A factor might have strong aggregate IC but only work in bull markets and fail catastrophically in bear markets — the LLM would never know, and would continue iterating on a regime-fragile factor. Adding per-regime performance data to the LLM feedback prompt lets the LLM judge factor robustness across market environments, leading to more generalizable factors.

## What Changes

- `process_results()` gains an optional `regime_map` parameter and returns a second string table with per-regime metrics (IC, annualized return, IR, max drawdown) in a side-by-side format
- The feedback prompt template gains a conditional `Regime-Aware Performance Analysis` block with interpretive guidance for the LLM
- `AlphaAgentLoop` loads the monthly regime map at init when `regime_aware_feedback` is enabled in config
- New `regime` config section (`regime_aware_feedback`, `regime_map_path`) — feature is opt-in, zero impact when disabled
- All metric computation reuses the pre-built `monthly_regime_map.csv` and existing `filter_dates_by_regime()` utility

## Capabilities

### New Capabilities
- `regime-aware-factor-feedback`: Enrich factor mining feedback prompts with per-regime performance breakdown tables, enabling the LLM to evaluate factor robustness across different market environments (calm_bull, calm_bear, volatile_bull, volatile_bear).

### Modified Capabilities
<!-- No existing spec requirements change -->

## Impact

- `quantaalpha/factors/feedback.py` — `process_results()` signature change (backward compatible), `generate_feedback()` wired to regime map
- `quantaalpha/factors/prompts/prompts.yaml` — new conditional template block
- `quantaalpha/pipeline/loop.py` — `AlphaAgentLoop.__init__()` loads regime map from config
- `quantaalpha/pipeline/factor_mining.py` — passes `regime` config to loop
- `configs/experiment.yaml` — new `regime` section fields
- `scripts/build_regime_map.py` — `load_regime_map()` and `filter_dates_by_regime()` imported as reusable utilities
