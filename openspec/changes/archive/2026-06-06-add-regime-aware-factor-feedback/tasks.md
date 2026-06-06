## 1. Config and wiring

- [x] 1.1 Add `regime` section to `configs/experiment.yaml` with `regime_aware_feedback: false` and `regime_map_path: "data/regime/monthly_regime_map.csv"`
- [x] 1.2 Pass `regime` config from `factor_mining.py` through to `AlphaAgentLoop.__init__()`
- [x] 1.3 In `AlphaAgentLoop.__init__()`, load regime map via `load_regime_map()` when `regime_aware_feedback` is `true`; store on `self.regime_map`; log warning if map file missing

## 2. Per-regime metric computation

- [x] 2.1 Add `build_regime_table(exp, regime_map)` function in `feedback.py` to load factor values from workspace, compute daily IC via Qlib, and group by regime
- [x] 2.2 Implement per-regime slicing: map each trading day to regime via monthly regime map; group daily IC by regime
- [x] 2.3 Build side-by-side Markdown table with columns per regime, rows for IC / annualized return / IR / max drawdown / n_trading_days
- [x] 2.4 Handle edge cases: missing workspace files → skip factor; missing Qlib labels → return None; regime < 20 trading days → `*low sample` annotation; no overlap → return None

## 3. Feedback prompt template

- [x] 3.1 Add `{% if regime_table %}` block to `factor_feedback_generation.user` in `quantaalpha/factors/prompts/prompts.yaml` with regime label descriptions, interpretive guidance, and `{{ regime_table }}` placeholder

## 4. Wire feedback method

- [x] 4.1 In `AlphaAgentQlibFactorHypothesisExperiment2Feedback.generate_feedback()`, compute `regime_table` from `build_regime_table()` and pass to template rendering
- [x] 4.2 Ensure `QlibFactorHypothesisExperiment2Feedback.generate_feedback()` retains backward compatibility (passes `regime_table=None`)

## 5. Tests

- [x] 5.1 Unit: `build_regime_table()` with mock experiment and regime map → verifies per-regime IC table is generated
- [x] 5.2 Unit: `build_regime_table()` with `regime_map=None` → returns `None`
- [x] 5.3 Unit: missing workspace result files → returns `None`
- [x] 5.4 Unit: low-sample regime → `*low sample` annotation present
- [x] 5.5 Unit: no overlap between result dates and regime map → returns `None`
- [x] 5.6 Integration: `generate_feedback()` with regime enabled → prompt contains regime section
- [x] 5.7 Integration: `generate_feedback()` with regime disabled → prompt identical to pre-change
