## ADDED Requirements

### Requirement: RegimeStrategy protocol
The system SHALL define a `RegimeStrategy` Protocol with a `detect(prices, vol_window, n_regimes) -> pd.Series` method that returns regime labels indexed by datetime.

#### Scenario: Custom strategy implementation
- **WHEN** a class implements `detect(prices: pd.Series, vol_window: int, n_regimes: int) -> pd.Series`
- **THEN** it SHALL be accepted by `MarketRegimeDetector` without inheritance (duck typing)

### Requirement: VolatilityDirectionStrategy default implementation
The system SHALL provide `VolatilityDirectionStrategy` that classifies market regime using two dimensions: rolling volatility (percentile-bucketed) and direction (cumulative return sign).

#### Scenario: Bear market detection
- **WHEN** the selection window cumulative return is negative and volatility is above the upper percentile threshold
- **THEN** the strategy SHALL return regime label `"volatile_bear"` for all dates in the window

#### Scenario: Bull market detection
- **WHEN** the selection window cumulative return is positive and volatility is below the lower percentile threshold
- **THEN** the strategy SHALL return regime label `"calm_bull"` for all dates in the window

#### Scenario: Insufficient data
- **WHEN** the price series has fewer than `vol_window` data points
- **THEN** the strategy SHALL return `None` for dates where volatility cannot be computed

### Requirement: MarketRegimeDetector facade
The system SHALL provide `MarketRegimeDetector` with `detect()` (full time series) and `dominant_regime()` (majority vote per window) methods.

#### Scenario: Dominant regime extraction
- **WHEN** `dominant_regime()` is called on a regime series containing 60% `"volatile_bear"` and 40% `"calm_bear"`
- **THEN** it SHALL return `"volatile_bear"`

#### Scenario: Tie-breaking
- **WHEN** `dominant_regime()` encounters equal counts of two regimes
- **THEN** it SHALL return the regime that appears first chronologically

### Requirement: Pluggable strategy via RegimeStrategy protocol
The `MarketRegimeDetector` SHALL accept any object implementing `RegimeStrategy` Protocol, enabling future strategy additions without modifying the detector.

#### Scenario: Strategy injection
- **WHEN** `MarketRegimeDetector(TrendStrategy())` is constructed
- **THEN** `detect()` SHALL delegate to `TrendStrategy.detect()`
