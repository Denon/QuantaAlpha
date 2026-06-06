## Context

The walk-forward backtest system (`quantaalpha/backtest/`) currently selects factors purely by IC/ICIR ranking within each fold's selection window, with no awareness of the prevailing market environment. Prior runs show poor performance (mean annualized return -22.5%), suggesting factor selection lacks contextual adaptation. Factor investing research shows that factor returns exhibit regime-dependent persistence — certain factors consistently outperform in specific market environments (e.g., low-volatility factors in bear markets).

The existing architecture has:
- `WalkForwardConfig` (frozen dataclass, 10 fields)
- `WalkForwardBacktestRunner` orchestrating fold generation → factor selection → backtest
- `select_top_factors()` in `factor_selection.py` doing IC-based ranking
- `FoldResult` / `WalkForwardResult` dataclasses for output

## Goals / Non-Goals

**Goals:**
- Add market regime detection as a pluggable, extensible module
- Label each fold with a regime tag based on its selection window's market conditions
- Output regime-aggregated factor performance summaries for downstream use
- Enable filtering historical folds by regime to identify factors effective in current market state
- Maintain full backward compatibility (no regime configured = identical behavior)

**Non-Goals:**
- Smooth regime transitions (预留接口 only, hard switch for now)
- Per-factor regime-specific IC breakdown (factor-level granularity)
- Changing fold structure or factor selection ranking logic
- Composite multi-signal regime detection (future via `RegimeStrategy` protocol)
- Real-time regime detection for live trading

## Decisions

### 1. Separate `regime.py` module with Protocol-based strategy pattern

**Choice:** New module `quantaalpha/backtest/regime.py` with `RegimeStrategy` Protocol, `VolatilityDirectionStrategy` default, and `MarketRegimeDetector` facade.

**Alternatives considered:**
- Inline in `factor_selection.py`: Simpler but couples concerns; factor selection already does one thing well
- Inline in `walk_forward.py`: Makes the already-complex runner harder to navigate

**Rationale:** Isolation enables independent testing, clear extension point for future signals (trend, composite), and keeps `factor_selection.py` focused on IC-based ranking.

### 2. Regime computed from selection window data (not prior data)

**Choice:** Use the selection window's own price data to determine regime. The label reflects "what environment factors were selected under."

**Alternatives considered:**
- Prior-window lookahead: Use data before the selection window to predict regime. Requires assumption that past regime predicts current — fragile.

**Rationale:** Avoids lookahead bias, uses actual observed conditions, simpler to reason about and validate.

### 3. Fold-level labeling with majority vote

**Choice:** Each fold gets one regime label via majority vote across its selection window dates.

**Alternatives considered:**
- Per-date regime labels within fold: More granular but adds complexity; the user's use case is fold-level filtering
- Weighted vote by recency: More sophisticated but unnecessary for v1

**Rationale:** Simple, stable, aligned with how the user thinks about folds as experiment units. Majority vote handles boundary cases within a window.

### 4. Volatility + Direction二维 classification

**Choice:** Combine rolling volatility (bucketed by percentile) with direction (cumulative return sign) → 4 labels: `calm_bull`, `calm_bear`, `volatile_bull`, `volatile_bear`.

**Alternatives considered:**
- Volatility only: Misses direction — high vol in bull vs bear are very different environments
- More complex signals (ADX, MA crossovers): Over-engineered for v1; Protocol interface allows adding later

**Rationale:** Two orthogonal dimensions capture the most important regime distinctions. Volatility bucketing via percentile is adaptive to different market periods.

### 5. Config: 3 new optional fields with safe defaults

**Choice:** Add `regime_method: str = ""`, `regime_vol_window: int = 60`, `regime_n_regimes: int = 2` to `WalkForwardConfig`.

**Alternatives considered:**
- Separate `RegimeConfig` dataclass: Cleaner separation but adds config loading complexity and a new YAML section
- Hardcoded regime parameters: Less flexible, harder to tune

**Rationale:** Empty `regime_method` disables the feature entirely (zero overhead). Defaults are conservative. Reuses existing config loading pattern.

### 6. Regime in output, not in factor selection logic

**Choice:** `select_top_factors()` remains unchanged. Regime is metadata on `FoldResult` and in output files. The selection logic continues to use IC/ICIR ranking on the full selection window.

**Alternatives considered:**
- Filter selection window by regime before computing IC: Would narrow the date range, reducing sample size; more complex; changes selection behavior

**Rationale:** Regime awareness is for analysis and downstream decision-making, not for altering the IC computation. The user selects factors based on IC, then uses regime to understand context and filter results.

### 7. Fold-level regime filtering via `regime_filter` config

**Choice:** Add `regime_filter: str = ""` to `WalkForwardConfig` and `--regime` CLI flag. When non-empty, folds whose `dominant_regime()` does not match are skipped. The fold's regime is computed identically — `regime_filter` only gates whether the fold proceeds to factor selection and backtest.

**Alternatives considered:**
- Monthly filtering within a fold: Would require restructuring `select_top_factors()` to accept date masks, breaking the design decision to keep factor selection unchanged.
- Post-hoc filtering of output files: Simpler but wastes compute on unwanted folds.

**Rationale:** Fold-level filtering is a single `if` statement in the runner loop, reuses the existing `dominant_regime()` call, and does not touch factor selection logic. The monthly regime map (`data/regime/monthly_regime_map.csv`) remains available as a standalone research tool for finer-grained analysis.

## Risks / Trade-offs

- **Regime stability** → Mitigated by using large `vol_window` (default 60 days) and majority vote. User can tune via config.
- **Regime heterogeneity within window** → A 6-month window may span sub-regimes. Acceptable for v1; future work could subdivide.
- **No smooth transitions** → Hard regime switches may cause factor set to change abruptly.预留 Protocol interface for future smooth blending.
- **Output format change** → `walk_forward_folds.json` and CSV gain new fields. Downstream parsers must handle new fields gracefully (default values if absent).
