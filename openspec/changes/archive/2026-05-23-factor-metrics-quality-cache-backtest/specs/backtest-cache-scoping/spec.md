## ADDED Requirements

### Requirement: Scoped cache key generation
The system SHALL generate backtest cache keys as an MD5 hash of the tuple `(expression, market_identifier, date_start, date_end, provider_uri, label_expr)`.

#### Scenario: Different market produces different cache key
- **WHEN** the same factor expression is computed for `csi300` vs `csi500` with identical date range and provider
- **THEN** the cache keys SHALL differ

#### Scenario: Different date range produces different cache key
- **WHEN** the same factor expression is computed for the same market and provider but different date ranges
- **THEN** the cache keys SHALL differ

#### Scenario: Same scope produces identical cache key
- **WHEN** the same expression, market, date range, and provider URI are used
- **THEN** the cache key SHALL be identical, enabling cache reuse

### Requirement: Cache instrument validation on read
The system SHALL validate that cached factor data contains instruments matching the configured market universe before returning a cache hit. Overlap SHALL be defined as `len(cached_instruments ∩ market_instruments) / len(cached_instruments)`.

#### Scenario: Cache instruments match configured market
- **WHEN** a cached factor's instrument overlap with the configured market is >= 0.80
- **THEN** the cache hit SHALL be accepted

#### Scenario: Cache instruments do not match configured market
- **WHEN** a cached factor's instrument overlap with the configured market is < 0.80
- **THEN** the cache SHALL be rejected and the factor SHALL be recomputed

### Requirement: Cache write with scoped key
The system SHALL write new cache entries using the scoped key format, so future runs can find and validate them.

#### Scenario: Recomputing after cache rejection writes scoped cache
- **WHEN** a legacy or mismatched cache is rejected and the factor is recomputed
- **THEN** the new result SHALL be cached with a scoped key (new filename), leaving the legacy unscoped file intact
