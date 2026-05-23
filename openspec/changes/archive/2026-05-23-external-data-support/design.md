## Context

Factor computation currently reads 6 price-volume fields from Qlib (`$open, $high, $low, $close, $volume, $vwap`) plus derived `$return`. These are the only columns available in the working DataFrame. Users want to introduce market capitalization, valuation ratios, and pre-computed signals from external sources.

The system has two separate factor computation paths:
1. **Backtest pipeline** — `CustomFactorCalculator` + `BacktestRunner` — evaluates factor expressions and runs backtests
2. **AI mining pipeline** — `FactorCalculator` + LLM — generates factor code from hypotheses, executes it, and feeds backtest results to the evolution loop

Both paths load data independently, both hardcode the same 6-field list. External data must reach both paths.

## Goals / Non-Goals

**Goals:**
- Load external data from CSV/Parquet files into a shared DataFrame format
- Make external columns available as `$`-prefixed fields in expression evaluation (both pipelines)
- Merge external columns as standalone features into the backtest dataset
- Expose external field names to the LLM prompt so it can reference them
- Compute per-factor IC metrics for external data columns
- Work when no custom computed factors exist (Qlib-only mode + external data)

**Non-Goals:**
- Live data fetching or automatic updates — files are static snapshots
- Data validation beyond format checks — trusted input
- Changes to `data_template/generate.py` — injection happens at runtime
- Frontend UI changes

## Decisions

### Decision 1: Shared `load_external_data()` utility over per-file inline loading

**Choice**: New file `quantaalpha/backtest/external_data.py` with a single `load_external_data(config)` function.

**Alternatives considered**:
- Inline loading in each caller — rejected because 3 callers (`get_qlib_stock_data`, `QlibDataProvider.get_stock_data`, `BacktestRunner.run`) need the same logic
- Qlib custom DataProvider — rejected because Qlib integration is heavy and doesn't add value for static file reading

**Rationale**: A ~30-line shared function is the right abstraction. Both pipelines get identical data. Future format additions (HDF5, SQL) extend it in one place.

### Decision 2: Columns get `$` prefix at injection time, not in the raw file

**Choice**: External CSV columns are named `market_cap`, `pe_ttm` in the file. The `$` prefix is added at injection time: `$market_cap`.

**Alternatives considered**:
- Requiring `$` prefix in the source file — rejected because it's unnatural for externally-managed data
- Using a separate namespace (e.g., `ext:market_cap`) — rejected because it breaks expression parser compatibility

**Rationale**: The expression parser expects `$`-prefixed column names. Keeping source files `$`-free makes them easier to generate and inspect. The `$` prefix is an internal convention.

### Decision 3: External columns are both base data AND standalone factors

**Choice**: External columns participate in two ways simultaneously:
1. As `$`-prefixed DataFrame columns usable in expressions (e.g., `$market_cap / $close`)
2. As standalone feature columns merged into the backtest dataset

**Alternatives considered**:
- Separate config for "base data" vs "pre-computed factors" — rejected as over-engineering; every column is useful both ways
- Opt-in flag per column — rejected as premature complexity

**Rationale**: A column like `market_cap` is useful as a standalone factor AND as a building block in expressions. Forcing the user to choose adds configuration burden with no benefit.

### Decision 4: Inject into existing data loading, not a new pipeline step

**Choice**: External data is loaded inside `get_qlib_stock_data()` and `QlibDataProvider.get_stock_data()`, making it part of the raw DataFrame.

**Alternative**: Add external data as a separate parameter flowing through the pipeline — rejected because it adds complexity to every intermediate method signature. Injecting early means downstream code (expression parser, LLM prompt) works unchanged.

### Decision 5: Column descriptions in config, separate from data loading

**Choice**: Add an optional `columns` mapping per file entry in `external_data.files[].columns`. A separate function `get_column_descriptions(config)` extracts the mapping without touching `load_external_data()`.

**Alternatives considered**:
- Embed descriptions in the CSV header via comments or multi-row headers — rejected because it breaks standard CSV tooling
- Include descriptions in `load_external_data()` return value — rejected because it changes the existing API and forces all callers to handle an extra return value

**Rationale**: Column descriptions are an opt-in enhancement. A standalone function keeps the data loading path unchanged (backward compatible) while providing an explicit hook for the LLM prompt layer to pull descriptions when available.

### Decision 6: Registration script for manual factor import into library

**Choice**: Provide `scripts/register_external_factor.py` that writes directly into `all_factors_library.json` with `factor_source: "external"` and `evolution_phase: "manual_import"` metadata.

**Alternatives considered**:
- Auto-registration from CSV columns — rejected because a CSV column has no `factor_description`, `factor_formulation`, or hypothesis context that the library schema expects
- Separate "external factors" JSON file — rejected because it adds a new factor source type to `FactorLoader`, duplicating library management logic

**Rationale**: The factor library schema already carries all the metadata LLM needs (`factor_expression`, `factor_description`, `factor_formulation`). Registering external factors directly into the library reuses the existing AI pipeline's library-aware prompting without adding new code paths. The script is a convenience — users can also edit the JSON by hand.

## Risks / Trade-offs

- **[Risk] Large external files increase memory** → Mitigation: Files are read once and joined to existing DataFrame. Parquet support gives compression options. No in-memory copy beyond what Qlib data already requires.
- **[Risk] External columns with NaN in Qlib date range gaps** → Existing `Fillna` preprocessor handles this. No special logic needed.
- **[Risk] External instrument codes mismatch Qlib codes** → Index intersection drops unmatched rows silently. User sees fewer data points and must debug. A warning is logged with the intersection size.
- **[Trade-off] No versioning or provenance tracking for external data** → By design (non-goal). Users manage their own external data versioning. The `metric_context` in factor metrics records the config hash but not external file checksums.
