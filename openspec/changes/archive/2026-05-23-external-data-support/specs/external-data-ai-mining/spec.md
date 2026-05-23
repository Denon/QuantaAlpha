## ADDED Requirements

### Requirement: External columns injected into AI pipeline data loading
The system SHALL inject external data columns with `$` prefix into the DataFrame returned by `QlibDataProvider.get_stock_data()`, making them available for LLM-generated factor code execution.

#### Scenario: External columns in QlibDataProvider output
- **WHEN** external data is configured
- **THEN** `QlibDataProvider.get_stock_data()` returns a DataFrame containing `$market_cap` etc. alongside default Qlib fields

### Requirement: External factors in library are visible to AI mining pipeline
The system SHALL include external factors registered in `all_factors_library.json` (with `factor_source: "external"` metadata) in the factor library loaded by the AI mining pipeline. Their `factor_description` and `factor_formulation` SHALL be provided to the LLM in the same way as AI-generated factors.

#### Scenario: External factor visible in library
- **WHEN** `all_factors_library.json` contains an entry with `factor_source: "external"`, `factor_description: "Total market cap..."`, and `factor_formulation: "MC = P × S"`
- **THEN** the AI mining pipeline's factor library includes this factor with its description and formulation available to the LLM

## MODIFIED Requirements

### Requirement: LLM prompt includes external field names
The system SHALL dynamically update the system prompt in `FactorCalculator._generate_factor_code()` to list all available `$`-prefixed columns from the working DataFrame, including external ones. Each column SHALL be listed with its description when one is available (from config `columns` mapping or from built-in descriptions for Qlib native fields).

#### Scenario: Prompt updated with external fields and descriptions
- **WHEN** the DataFrame contains columns `$open, $close, $volume, $market_cap, $pe_ttm` AND column descriptions are available for `$market_cap` and `$pe_ttm`
- **THEN** the LLM system prompt lists all five fields as a description list, with `$market_cap` and `$pe_ttm` accompanied by their descriptions, and Qlib native fields accompanied by built-in descriptions (e.g., "$open: Opening price")

#### Scenario: No descriptions, prompt lists bare field names
- **WHEN** no column descriptions are configured
- **THEN** the prompt lists only the field names, matching the original behavior

#### Scenario: No external data, prompt uses built-in Qlib descriptions
- **WHEN** no external data is configured
- **THEN** the prompt lists default Qlib fields with built-in descriptions
