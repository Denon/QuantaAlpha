## ADDED Requirements

### Requirement: Compact regime summary on factor cards

On the Factor Library page, each factor card SHALL display a single-line best/worst regime summary below the existing IC metrics grid. The summary SHALL show the `best_regime` name and its Rank IC value, and the `worst_regime` name and its Rank IC value. The summary SHALL only appear when `factor.regimeSummary` exists and contains valid data.

#### Scenario: Card shows regime summary when data exists
- **WHEN** a factor has `regimeSummary` with `best_regime: "calm_bull"` (Rank IC 0.042) and `worst_regime: "volatile_bear"` (Rank IC 0.009)
- **THEN** the card displays "最佳环境: calm_bull (0.042) | 最差: volatile_bear (0.009)"

#### Scenario: Card hides regime summary when data is absent
- **WHEN** a factor has no `regimeSummary` field or the field is null/undefined
- **THEN** no regime summary line is rendered on the card

### Requirement: Full regime metrics table in detail modal

In the factor detail modal, a new section titled "不同市场环境表现" SHALL display a table with one row per regime. Each row SHALL show: regime label, Rank IC, IC, ICIR, hit rate (as percentage), and sample days. Rows SHALL be color-coded by performance tier (green for highest IC, yellow, orange, red for lowest). The section header SHALL include a badge showing the `regime_stability` score. The section SHALL only appear when `selectedFactor.regimeMetrics` exists.

#### Scenario: Modal shows full regime table
- **WHEN** a factor is clicked and the detail modal opens, and the factor has `regimeMetrics` with 4 regimes
- **THEN** the modal displays a "不同市场环境表现" section with a 4-row table containing Rank IC, IC, ICIR, hit rate, and sample days for each regime

#### Scenario: Modal hides regime section when data is absent
- **WHEN** a factor is clicked and the detail modal opens, and the factor has no `regimeMetrics`
- **THEN** the "不同市场环境表现" section is not rendered

#### Scenario: Regime stability badge shown
- **WHEN** the regime table section is displayed and `regimeSummary.regime_stability` is 0.62
- **THEN** a badge labeled "稳定性: 0.62" appears in the section header

### Requirement: Aggregate best-regime distribution stats card

The Factor Library page SHALL display an additional stats card titled "最佳环境分布" in the stats summary row. This card SHALL show, for each distinct regime label, the count of factors whose `regimeSummary.best_regime` matches that label. Factors without `regimeSummary` SHALL be excluded from the counts.

#### Scenario: Distribution card shows counts
- **WHEN** 50 factors are loaded, and 22 have `best_regime: "calm_bull"`, 15 "volatile_bull", 8 "calm_bear", 5 "volatile_bear"
- **THEN** the card displays a 4-line breakdown with these counts alongside each regime label

#### Scenario: Factors without regime data are excluded
- **WHEN** 10 of 50 factors lack `regimeSummary`
- **THEN** the distribution counts sum to 40, not 50

### Requirement: Regime filter dropdown

The filter bar on the Factor Library page SHALL include a `<select>` dropdown for filtering by best regime. The dropdown SHALL be positioned after the quality filter buttons, separated by a visual divider. It SHALL list all distinct regime labels found across factors' `regimeSummary.best_regime` values, with a count for each. Selecting a regime SHALL filter the displayed factors to only those whose `regimeSummary.best_regime` matches. The regime filter SHALL compose with the quality filter using AND logic. A default "全部环境" option SHALL show all factors.

#### Scenario: Regime filter narrows factor list
- **WHEN** the user selects "calm_bull" from the regime dropdown
- **THEN** only factors with `regimeSummary.best_regime: "calm_bull"` are displayed

#### Scenario: Regime filter combined with quality filter
- **WHEN** the user selects "高质量" quality filter AND "calm_bull" regime filter
- **THEN** only high-quality factors whose best regime is calm_bull are displayed

#### Scenario: Factors without regime data hidden when filter active
- **WHEN** any regime is selected in the filter dropdown
- **THEN** factors without `regimeSummary` are hidden from the list

#### Scenario: "全部环境" resets regime filter
- **WHEN** the user selects "全部环境" from the regime dropdown
- **THEN** all factors are shown (subject only to any active quality filter)
