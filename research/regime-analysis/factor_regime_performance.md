# Factor Performance by Market Regime

**Date**: 2026-06-03
**Data**: CSI 300, 189 months (2010-04 → 2025-12)
**Method**: Cross-sectional Rank IC, computed monthly via Alpha158 handler

## Tested Factors

| Factor | Type | Description |
|--------|------|-------------|
| `ROC5` | Momentum | 5-day rate of change |
| `ROC20` | Momentum | 20-day rate of change |
| `RSV5` | Oscillator | 5-day stochastic (Raw Stochastic Value) |

## Full Results

### ROC5 — Short-term Momentum

```
Regime           Months   Mean Rank IC   Std     Hit Rate   t-stat   p(ANOVA)
─────────────────────────────────────────────────────────────────────────────
volatile_bull      43        +0.0544     0.042     88%       +8.46
volatile_bear      54        +0.0316     0.046     70%       +5.02    0.0009
calm_bull          52        +0.0228     0.041     65%       +3.98    (✓)
calm_bear          40        +0.0183     0.047     70%       +2.46
```

**Conclusion**: ROC5 works best in volatile bull markets. The IC in `volatile_bull` is 3× that of `calm_bear`. The hit rate (88%) means ROC5 correctly predicted the direction of next-day returns in 88% of volatile_bull months.

### ROC20 — Long-term Momentum

```
Regime           Months   Mean Rank IC   Std     Hit Rate   t-stat   p(ANOVA)
─────────────────────────────────────────────────────────────────────────────
volatile_bull      43        +0.0376     0.034     88%       +7.30
volatile_bear      54        +0.0179     0.056     61%       +2.33    0.0419
calm_bull          52        +0.0125     0.041     56%       +2.18    (✓)
calm_bear          40        +0.0111     0.058     62%       +1.21
```

**Conclusion**: Similar pattern to ROC5 but weaker. Long-term momentum is more regime-dependent — the IC drops by 70% from volatile_bull to calm_bear.

### RSV5 — 5-day Stochastic Oscillator

```
Regime           Months   Mean Rank IC   Std     Hit Rate   t-stat   p(ANOVA)
─────────────────────────────────────────────────────────────────────────────
volatile_bull      43        -0.0501     0.037      9%       -8.97
volatile_bear      54        -0.0202     0.045     33%       -3.34    0.0001
calm_bull          52        -0.0160     0.035     35%       -3.29    (✓)
calm_bear          40        -0.0139     0.047     30%       -1.89
```

**Conclusion**: RSV5 is a consistent mean-reversion signal (negative IC in ALL regimes). The reversal effect is strongest in `volatile_bull` — when the market is surging, overbought stocks revert hardest. Only 9% of months show positive IC, meaning RSV5's contrarian signal is reliable.

## Cross-Factor Patterns

```
                         ROC5        ROC20       RSV5
volatile_bull            ████████    ███████     ██████████ (reversal)
volatile_bear            █████       ████        ████
calm_bull                ████        ███         ███
calm_bear                ███         ██          ██
```

- **volatile_bull** = strongest signals overall (both momentum and reversal)
- **calm_bear** = weakest signals overall (all ICs near zero)
- Momentum factors trend together; RSV5 is anti-correlated

## Hypotheses for Future Investigation

1. **"Regime-first" factor selection**: Instead of top-k by IC, first classify current regime, then select factors known to work in that regime
2. **RSV5 as regime indicator**: The magnitude of RSV5's negative IC could itself signal regime transitions
3. **Composite regime signals**: Add trend strength (ADX) or volume profile to improve regime classification stability
4. **Regime transition alpha**: Factors that work in the transition between regimes (e.g., calm_bull → volatile_bear)
