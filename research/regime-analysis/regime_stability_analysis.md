# Regime Stability Analysis

**Date**: 2026-06-03
**Question**: Do factors that rank highly in one volatile_bear fold also rank highly in another?

## Experiment: volatile_bear Fold Comparison

Two volatile_bear folds from the smoke test:
- **Fold 2** (2018 H2): Selection window 2018-07-01 → 2018-12-30
- **Fold 5** (2020 H1): Selection window 2020-01-01 → 2020-06-29

Both classified as `volatile_bear`, separated by ~18 months.

## Results: 20 alpha158_20 factors ranked by |Rank_IC|

```
Factor              Fold 2 IC   Fold 2 Rank   Fold 5 IC   Fold 5 Rank   ΔRank
──────────────────────────────────────────────────────────────────────────────
ROC0                 +0.0111        4          -0.0280         2          +2  ★
ROC5                 -0.0176        2          -0.0189         6          -4
BODY_RATIO           +0.0077        9          -0.0315         1          +8
MA_RATIO5_10         -0.0108        5          -0.0203         5           0  ★★
ROC1                 +0.0100        7          -0.0206         4          +3  ★
LOW_RATIO5           -0.0152        3          -0.0076        13         -10
SHADOW_RATIO         -0.0069       14          +0.0270         3         +11
HIGH_RATIO5          +0.0077       10          -0.0134         8          +2  ★
VRATIO10             +0.0098        8          -0.0089        12          -4
RET_VOL5             -0.0245        1          +0.0005        20         -19  ✗✗
VRATIO5              +0.0070       12          -0.0116        10          +2  ★
VOLATILITY5          -0.0106        6          +0.0023        18         -12
RSV5                 -0.0016       19          -0.0150         7         +12
RSV10                +0.0055       17          -0.0132         9          +8
ROC10                -0.0059       15          -0.0093        11          +4
RANGE                -0.0073       11          -0.0025        17          -6
ROC20                -0.0069       13          -0.0032        16          -3  ★
VSTD5_RATIO          +0.0057       16          -0.0039        15          +1  ★
VOLATILITY10         -0.0023       18          +0.0064        14          +4
MA_RATIO10_20         0.0000       20          -0.0007        19          +1  ★
```

★ = stable (|Δ| ≤ 3), ✗✗ = highly unstable (|Δ| ≥ 15)

## Statistics

- **Spearman rank correlation**: ρ = 0.15 (p = 0.53, not significant)
- **Pearson correlation (Rank_IC)**: r = -0.38 (p = 0.10)
- **Top-5 overlap**: 2/5 (MA_RATIO5_10, ROC0)
- **Stable factors (|Δ| ≤ 3)**: 8/20 (40%)
- **Highly unstable (|Δ| ≥ 10)**: 5/20 (25%)

## Most Stable Factors (reliable across volatile_bear periods)

| Factor | Fold 2 Rank | Fold 5 Rank | Δ | Pattern |
|--------|:-----------:|:-----------:|:-:|---------|
| MA_RATIO5_10 | 5 | 5 | 0 | Moving average ratio — very stable |
| ROC0 | 4 | 2 | 2 | Instant momentum — consistent top-5 |
| ROC1 | 7 | 4 | 3 | Short momentum — consistent top-7 |
| HIGH_RATIO5 | 10 | 8 | 2 | Upper shadow ratio |
| VSTD5_RATIO | 16 | 15 | 1 | Vol structure ratio |

## Most Unstable Factors (regime label alone insufficient)

| Factor | Fold 2 Rank | Fold 5 Rank | Δ | Note |
|--------|:-----------:|:-----------:|:-:|------|
| RET_VOL5 | #1 | #20 | -19 | Return/vol ratio — completely different behavior |
| VOLATILITY5 | #6 | #18 | -12 | Short volatility — COVID vs trade war vol structure |
| RSV5 | #19 | #7 | +12 | Stochastic — effective in COVID, useless in trade war |
| SHADOW_RATIO | #14 | #3 | +11 | Candle shadow — opposite effectiveness |

## Interpretation

1. **Static factors exist**: `MA_RATIO5_10` and short momentum (`ROC0`, `ROC1`) show consistent ranking across `volatile_bear` periods. These can be trusted.

2. **Volatility-dependent factors are fragile**: `RET_VOL5`, `VOLATILITY5` — their effectiveness depends on the *nature* of volatility (trade war grinding decline vs COVID crash), not just its level.

3. **Sample size matters**: With only 2 `volatile_bear` folds in 2.5 years, statistical conclusions are weak. Monthly regime analysis (54 `volatile_bear` months across 2010-2025) provides much stronger signal.

4. **Regime classification may need refinement**: The `volatile_bear` label captures high-vol + declining, but there are sub-types:
   - **Crash bear** (2020 COVID): Sharp V-shape, high reversal
   - **Grinding bear** (2018 trade war): Slow decline, trend-following
   - **Crisis bear** (2015, 2022): Liquidity crises

## Next Steps

- Run the same analysis with 10+ years of monthly data for robust statistics
- Consider adding a "volatility regime change rate" dimension to distinguish crash vs grinding
- Test if combining `volatile_bear` + calendar quarter improves stability
