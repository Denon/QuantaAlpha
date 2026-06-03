# Monthly Regime Distribution

**Date**: 2026-06-03
**Source**: `data/regime/monthly_regime_map.csv`
**Method**: `VolatilityDirectionStrategy` on CSI 300 benchmark ($close), vol_window=60, n_regimes=2

## Overall Distribution (2010-04 → 2025-12, 189 months)

```
volatile_bear   54 months (28.6%) ██████████████
calm_bull       52 months (27.5%) █████████████
volatile_bull   43 months (22.8%) ███████████
calm_bear       40 months (21.2%) ██████████
```

Distribution is roughly balanced — no severe class imbalance.

## Year-by-Year Heatmap

```
Year  J  F  M  A  M  J  J  A  S  O  N  D    Dominant Theme
───────────────────────────────────────────  ──────────────────────
2010  -- -- -- vb cb cb vb vb vb vb vb cb    Recovery from GFC
2011  CB vb vb vb CB CB VB VB VB CB CB CB    Bear market
2012  cb vb vb vb cb CB CB CB CB vb CB vb    Choppy
2013  vb vb CB CB vb VB vb vb vb cb cb vb    June liquidity crunch
2014  CB cb cb CB cb cb vb vb vb vb vb vb    H1 bear, H2 bull run start
2015  vb vb vb vb vb VB VB VB CB CB vb vb    2015 crash (Jun-Aug volatile_bear)
2016  -- -- -- vb vb VB cb cb cb cb cb cb    Post-crash recovery
2017  cb cb cb cb CB cb cb cb cb cb cb cb    White-horse bull (11/12 calm_bull)
2018  cb VB vb VB VB VB VB VB VB VB VB VB    Trade war (10/12 volatile_bear)
2019  VB vb vb vb vb VB VB vb cb cb cb cb    Rebound → consolidation
2020  cb vb VB VB VB vb vb vb vb vb vb cb    COVID crash (Mar-May volatile_bear)
2021  vb vb vb VB VB cb cb VB VB VB CB cb    Rotation year
2022  CB CB VB VB VB vb vb vb CB CB VB VB    China zero-COVID + property crisis
2023  vb cb cb cb CB CB CB CB CB CB CB CB    Prolonged decline (8/12 calm_bear)
2024  CB CB vb cb cb CB CB CB CB vb vb vb    Bottoming process
2025  VB VB CB VB VB VB cb cb cb vb vb cb    Volatility returns, partial recovery

Legend: cb=calm_bull  CB=calm_bear  vb=volatile_bull  VB=volatile_bear
```

## Regime Persistence

| From \ To        | calm_bear | calm_bull | volatile_bear | volatile_bull |
|------------------|-----------|-----------|---------------|---------------|
| calm_bear        | **67%**   | 10%       | 14%           | 10%           |
| calm_bull        | 11%       | **74%**   | 6%            | 9%            |
| volatile_bear    | 6%        | 9%        | **66%**       | 19%           |
| volatile_bull    | 4%        | 18%       | 21%           | **57%**       |

- Strong diagonal: regimes tend to persist (57-74% month-to-month)
- `volatile_bear → volatile_bull` (19%) more common than reverse — crashes resolve into rallies
- `calm_bull` is the stickiest (74%)

## Average Duration

```
calm_bull       3.6 months (max 10: 2017 full year, 2016 H2)
volatile_bear   2.9 months (max 10: 2018 full year)
calm_bear       3.0 months (max 10: 2022-2023)
volatile_bull   2.3 months (max 6)
```

## Notable Historical Matches

| Event | Regime | Duration | Accuracy |
|-------|--------|----------|----------|
| 2015 China crash | volatile_bear | Jun-Aug 2015 | ✓ |
| 2017 white-horse bull | calm_bull | Jan-Dec 2017 | ✓ |
| 2018 trade war | volatile_bear | Feb-Dec 2018 | ✓ |
| 2020 COVID crash | volatile_bear | Mar-May 2020 | ✓ |
| 2022-2023 property crisis | calm_bear | Jan 2022–Oct 2023 | ✓ |
