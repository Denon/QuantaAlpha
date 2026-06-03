# Regime Analysis Research Notes

Market regime detection and factor performance analysis. Data covers CSI 300 (2010–2025).

## Files

| File | Description |
|------|-------------|
| `factor_regime_performance.md` | Factor IC by regime — which factors work in which environment |
| `monthly_regime_distribution.md` | Regime calendar — monthly labels and historical context |
| `regime_stability_analysis.md` | Cross-fold factor rank stability within the same regime |

## Key Findings (quick reference)

1. **Momentum factors (ROC5, ROC20) excel in `volatile_bull`** — 88% monthly hit rate
2. **All factors weaken in `calm_bear`** — mean IC drops to near zero
3. **RSV5 is a consistent contrarian signal** — negative IC in all regimes, strongest reversal in `volatile_bull`
4. **Regime effect is statistically significant** — ANOVA p < 0.05 for all tested factors
5. **Same-regime factor ranking is not perfectly stable** — Spearman ρ=0.15 across 2018H2 vs 2020H1 `volatile_bear` folds (n=2 only)

## Tools

- `scripts/build_regime_map.py` — Rebuild the monthly regime map
- `scripts/test_factors_by_regime.py` — Test any alpha158 factor across regimes
- `scripts/demo_regime_filter.py` — Regime-filtered factor query
- `data/regime/monthly_regime_map.csv` — Pre-built 189-month regime classification

## Related Specs

- `openspec/specs/market-regime-detection/spec.md`
- `openspec/specs/regime-aware-factor-selection/spec.md`
