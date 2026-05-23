## ADDED Requirements

### Requirement: Register external factor into library
The system SHALL provide a CLI script `scripts/register_external_factor.py` that adds a factor entry to `data/factorlib/all_factors_library.json` with `factor_source: "external"` and `evolution_phase: "manual_import"` in metadata.

#### Scenario: Successful registration
- **WHEN** the script is invoked with `--name "market_cap_factor" --expression "$market_cap" --description "Total market cap" --formulation "MC = P \\times S" --library data/factorlib/all_factors_library.json`
- **THEN** the library JSON is updated with a new factor entry containing the provided name, expression, description, and formulation, with an auto-generated `factor_id`

#### Scenario: Factor name conflict
- **WHEN** a factor with the same `factor_name` already exists in the library
- **THEN** the script raises an error and does not modify the library

#### Scenario: Force overwrite on conflict
- **WHEN** a factor with the same `factor_name` exists AND `--force` is passed
- **THEN** the script overwrites the existing entry with the new data

### Requirement: Registration metadata
Registered factors SHALL have `factor_source: "external"` and `evolution_phase: "manual_import"` set in their metadata. `factor_metrics` SHALL be set to `null` until backfilled by `scripts/backfill_factor_metrics.py`.

#### Scenario: Metadata fields set correctly
- **WHEN** a factor is registered
- **THEN** its metadata contains `{"factor_source": "external", "evolution_phase": "manual_import", "created_at": "<current ISO timestamp>"}` and `factor_metrics` is `null`

### Requirement: Library metadata updated
The script SHALL update the `metadata.last_updated` timestamp and `metadata.total_factors` count after adding a new factor.

#### Scenario: Library stats updated
- **WHEN** a library with 29 factors has one new factor registered
- **THEN** `total_factors` becomes 30 and `last_updated` reflects the current time
