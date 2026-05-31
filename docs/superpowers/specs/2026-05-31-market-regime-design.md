# Market Regime Detection for Walk-Forward Factor Selection

## Goal

Add market regime awareness to the walk-forward factor selection backtest, so factors can be evaluated and selected within the context of the prevailing market environment. The core hypothesis is that factor performance has continuity within同类市场环境 — factors that perform well in a given regime (e.g., bear market) tend to continue performing well as long as that regime persists.

## Design Decisions

### 1. Regime Signal: Volatility + Direction (二维分类)

- **Volatility**: rolling window standard deviation of market returns, bucketed by percentile into `n_regimes` tiers (e.g., low/high)
- **Direction**: cumulative return over the selection window; positive = bull, negative = bear
- **Combined labels**: `calm_bull`, `calm_bear`, `volatile_bull`, `volatile_bear`

### 2. Regime Detection Timing

Regime is computed using data **within the selection window** (after it ends), not from prior data. This avoids lookahead bias and reflects the actual environment under which factors were selected.

### 3. Fold-Level Regime Labeling

Each fold receives one regime label (the dominant regime within its selection window). Factor selection logic (`select_top_factors`) is unchanged — regime does not affect IC computation. The label is purely metadata for filtering and analysis.

### 4. Transition Handling

Hard switch for now. The architecture预留 smooth transition interface (`RegimeStrategy` protocol) for future use.

## Architecture

### New Module: `quantaalpha/backtest/regime.py`

```python
class RegimeStrategy(Protocol):
    """Duck-typed strategy for regime detection. Implement detect() to add new signals."""
    def detect(self, prices: pd.Series, vol_window: int, n_regimes: int) -> pd.Series:
        """Returns pd.Series with index=datetime, value=regime label string."""
        ...

class VolatilityDirectionStrategy:
    """Default implementation: volatility bucketing + direction (bull/bear)."""
    def detect(self, prices: pd.Series, vol_window: int, n_regimes: int) -> pd.Series:
        # 1. Rolling volatility → percentile-based buckets
        # 2. Cumulative return over full window → bull/bear
        # 3. Combine into二维 labels
        ...

class MarketRegimeDetector:
    """Facade: takes a strategy, runs detection, provides date-level queries."""
    def __init__(self, strategy: RegimeStrategy): ...
    def detect(self, prices: pd.Series, vol_window: int, n_regimes: int) -> pd.Series: ...
    def dominant_regime(self, regime_series: pd.Series) -> str:
        """Returns the most frequent regime label (majority vote) over the series."""
        ...
```

**Key design points:**
- `RegimeStrategy` uses Protocol (duck typing), not ABC — new signals don't need inheritance
- `detect()` returns a full time series; `dominant_regime()` reduces to a single label per fold
- Prices input is a market-wide aggregate (e.g., equal-weight index return series), passed from the runner

### Config Changes: `WalkForwardConfig`

Three new optional fields (frozen dataclass, defaults preserve backward compatibility):

```python
regime_method: str = ""          # "" = disabled, "volatility_direction" = volatility + direction
regime_vol_window: int = 60      # Rolling window (trading days) for volatility calculation
regime_n_regimes: int = 2        # Volatility tiers (direction is always 2: bull/bear)
```

**Config loading** in `load_walk_forward_config`:

```python
regime_method=wf.get("regime_method", ""),
regime_vol_window=int(wf.get("regime_vol_window", 60)),
regime_n_regimes=int(wf.get("regime_n_regimes", 2)),
```

**User config example:**

```yaml
walk_forward:
  enabled: true
  regime_method: "volatility_direction"
  regime_vol_window: 60
  regime_n_regimes: 2
```

### Runner Integration

In `WalkForwardBacktestRunner.run()`, after generating folds and before the fold loop:

```python
# Compute market-wide price series once (e.g., equal-weight index)
market_prices = compute_market_prices(features_df)  # helper function

for fold in folds:
    # 1. Compute regime for this fold's selection window
    if self.config.regime_method:
        detector = MarketRegimeDetector(VolatilityDirectionStrategy())
        selection_prices = market_prices[fold.selection_start:fold.selection_end]
        regime_series = detector.detect(selection_prices, ...)
        regime_label = detector.dominant_regime(regime_series)
    else:
        regime_label = None

    # 2. Factor selection (unchanged)
    selection = select_top_factors(...)

    # 3. Store regime in FoldResult
    fold_results.append(FoldResult(..., regime=regime_label))
```

### Output Enhancements

**1. `walk_forward_folds.json`** — each fold gains `regime` field:

```json
{
  "fold_id": 1,
  "selection_start": "2018-01-01",
  "selection_end": "2018-06-30",
  "regime": "volatile_bear",
  "selected_factors": ["factor_A", "factor_B"],
  "metrics": { ... }
}
```

**2. New file: `walk_forward_regime_summary.json`** — per-regime aggregated factor performance:

```json
{
  "volatile_bear": {
    "n_folds": 3,
    "avg_mean_ic": 0.028,
    "avg_mean_rank_icir": 0.15,
    "top_factors": ["factor_A", "factor_B", "factor_C"]
  },
  "calm_bull": {
    "n_folds": 5,
    "avg_mean_ic": 0.041,
    "avg_mean_rank_icir": 0.22,
    "top_factors": ["factor_D", "factor_E"]
  }
}
```

**3. `walk_forward_selected_factors.csv`** — gains `regime` column:

```csv
fold_id,factor_name,regime
1,factor_A,volatile_bear
1,factor_B,volatile_bear
2,factor_D,calm_bull
```

### Data Flow Summary

```
features_df ──┐
              ├── compute_market_prices() ──▶ market_prices
label_series ─┘                                    │
                                                   ▼
                                    MarketRegimeDetector.detect()
                                                   │
                                                   ▼
                                          regime_series (per date)
                                                   │
                                    dominant_regime() per fold
                                                   │
                                                   ▼
                                          regime_label (string)
                                                   │
                              ┌─────────────────────┤
                              ▼                     ▼
                    select_top_factors()    FoldResult.regime
                              │                     │
                              ▼                     ▼
                    selected factors        walk_forward_folds.json
                              │              (with regime field)
                              ▼
                    run_feature_frame()
                              │
                              ▼
                    _aggregate_metrics() + _save_result()
                              │
                              ▼
                    walk_forward_regime_summary.json (NEW)
```

## Testing Strategy

- **Unit tests for `regime.py`**: test `VolatilityDirectionStrategy.detect()` with synthetic price data, verify regime labels are correct for known patterns (e.g., monotonic decline → bear, monotonic increase → bull)
- **Unit tests for `MarketRegimeDetector.dominant_regime()`**: test majority vote logic, tie-breaking, all-same-regime case
- **Integration test**: mock runner, verify that `FoldResult.regime` is populated correctly when `regime_method` is set, and `None` when disabled
- **Backward compatibility test**: run without `regime_method` config, verify all outputs are identical to current behavior

## What's NOT in Scope

- Smooth transition between regimes (预留接口 only)
- Per-factor regime-specific IC breakdown (factor-level granularity)
- Changing fold structure or factor selection logic
- Adding new config options beyond the 3 specified
- Composite multi-signal regime detection (future extension via `RegimeStrategy` protocol)
