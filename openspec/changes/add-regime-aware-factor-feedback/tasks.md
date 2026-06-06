## 1. Config and wiring

- [ ] 1.1 Add `regime` section to `configs/experiment.yaml` with `regime_aware_feedback: false` and `regime_map_path: "data/regime/monthly_regime_map.csv"`
- [ ] 1.2 Pass `regime` config from `factor_mining.py` through to `AlphaAgentLoop.__init__()`
- [ ] 1.3 In `AlphaAgentLoop.__init__()`, load regime map via `load_regime_map()` when `regime_aware_feedback` is `true`; store on `self.regime_map`; log warning if map file missing

## 2. Per-regime metric computation

- [ ] 2.1 Extend `process_results()` signature: `regime_map=None` parameter; return `(str, str | None)` tuple
- [ ] 2.2 Implement per-regime slicing: for each unique regime label, call `filter_dates_by_regime()` to get date ranges, filter the backtest result, compute the same 4 metrics per subset
- [ ] 2.3 Build side-by-side DataFrame with columns per regime, rows for IC / annualized return / IR / max drawdown / n_trading_days
- [ ] 2.4 Handle edge cases: uncovered dates excluded, regime with < 20 trading days annotated with `*low sample`, no overlap → return `None`

## 3. Feedback prompt template

- [ ] 3.1 Add `{% if regime_table %}` block to `factor_feedback_generation.user` in `quantaalpha/factors/prompts/prompts.yaml` with regime label descriptions, interpretive guidance, and `{{ regime_table }}` placeholder

## 4. Wire feedback method

- [ ] 4.1 In `AlphaAgentQlibFactorHypothesisExperiment2Feedback.generate_feedback()`, accept and pass `regime_map` to `process_results()`; pass `regime_table` to template rendering
- [ ] 4.2 Ensure `QlibFactorHypothesisExperiment2Feedback.generate_feedback()` retains backward compatibility (no regime map → no regime section)

## 5. Tests

- [ ] 5.1 Unit: `process_results()` with mock regime map → verifies per-regime metrics and table format
- [ ] 5.2 Unit: `process_results()` with `regime_map=None` → returns `None` for regime_table, combined_result unchanged
- [ ] 5.3 Unit: partially overlapping date range → uncovered dates excluded, covered correctly grouped
- [ ] 5.4 Unit: low-sample regime → `*low sample` annotation present
- [ ] 5.5 Unit: no overlap between result dates and regime map → regime_table is `None`
- [ ] 5.6 Integration: `generate_feedback()` with regime enabled → prompt contains regime section with correct table
- [ ] 5.7 Integration: `generate_feedback()` with regime disabled → prompt identical to pre-change
