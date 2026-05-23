## ADDED Requirements

### Requirement: Load external data from CSV files
The system SHALL load external factor data from one or more CSV files specified in the `external_data.files` config section. Each file MUST contain a date column and an instrument column, with all remaining columns treated as factor values.

#### Scenario: Single CSV file loaded successfully
- **WHEN** config specifies one CSV file with columns `date, instrument, market_cap, pe_ttm`
- **THEN** the system returns a DataFrame with MultiIndex (datetime, instrument) and columns `[market_cap, pe_ttm]`

#### Scenario: File not found
- **WHEN** a specified file path does not exist
- **THEN** the system logs an error, skips the file, and continues loading remaining files

#### Scenario: Missing required columns
- **WHEN** a file is missing the configured date column or instrument column
- **THEN** the system raises a descriptive ValueError

#### Scenario: Empty file
- **WHEN** a specified file exists but contains no data rows
- **THEN** the system logs a warning and skips the file

### Requirement: Load external data from Parquet files
The system SHALL support Parquet as an alternative format, specified via `format: "parquet"` in the file config entry.

#### Scenario: Parquet file loaded
- **WHEN** config specifies a Parquet file with the required columns
- **THEN** the system returns a DataFrame identical in structure to CSV loading output

### Requirement: Merge multiple external data files
The system SHALL concatenate data from all specified files into a single DataFrame. Duplicate column names across files SHALL be deduplicated, keeping the first occurrence.

#### Scenario: Two files with overlapping column names
- **WHEN** file A has columns `[market_cap, pe_ttm]` and file B has columns `[market_cap, roe]`
- **THEN** the result contains columns `[market_cap, pe_ttm, roe]` with `market_cap` values from file A

### Requirement: No-op when config section absent
When the `external_data` section is absent from config or `files` is empty, the loader SHALL return `None` without error.

#### Scenario: Config section missing
- **WHEN** config has no `external_data` key
- **THEN** `load_external_data(config)` returns `None`

### Requirement: Column descriptions parsed from config
The system SHALL provide a `get_column_descriptions(config)` function that extracts optional column descriptions from the `columns` mapping in each file entry. Columns without descriptions SHALL be omitted from the result.

#### Scenario: Descriptions present
- **WHEN** a file entry has `columns: {market_cap: "Total market cap", pe_ttm: "Trailing P/E ratio"}`
- **THEN** `get_column_descriptions(config)` returns `{"market_cap": "Total market cap", "pe_ttm": "Trailing P/E ratio"}`

#### Scenario: No descriptions configured
- **WHEN** no file entry has a `columns` mapping
- **THEN** `get_column_descriptions(config)` returns an empty dict `{}`

#### Scenario: Mixed — some columns described, some not
- **WHEN** a file entry has `columns: {market_cap: "Total market cap"}` but also has an undescribed column `pe_ttm`
- **THEN** the result contains only `{"market_cap": "Total market cap"}`
