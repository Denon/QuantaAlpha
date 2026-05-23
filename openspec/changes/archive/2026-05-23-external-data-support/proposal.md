## Why

Factor computation is currently limited to 6 price-volume fields (`$open, $high, $low, $close, $volume, $vwap`) from Qlib. Users need to bring in external data — market capitalization, valuation ratios, or custom pre-computed signals — as both base columns for expression-based factor mining and as standalone factors for backtest.

## What Changes

- Add a shared external data loader that reads CSV or Parquet files with date/instrument keys
- Inject external columns (with `$` prefix) into the working DataFrame used by both the backtest expression parser and the AI mining pipeline, making them referencable in factor expressions
- Merge external columns as standalone factor features into the backtest dataset so pre-computed signals participate in training without needing wrapper expressions
- Compute per-factor IC metrics for external data columns alongside expression-based factors
- Update the LLM prompt in `FactorCalculator` to dynamically list available `$` fields including external ones, enabling AI-generated factors that reference new data

## Capabilities

### New Capabilities

- `external-data-loading`: Shared utility that loads external data from CSV/Parquet files, returning a MultiIndex (datetime, instrument) DataFrame. Handles multi-file dedup, missing file fallback, and configurable column name mapping.
- `external-data-backtest`: Injects external data columns into the backtest pipeline — both as `$`-prefixed DataFrame columns for expression evaluation in `CustomFactorCalculator`, and as standalone feature columns merged into the dataset before model training. Includes per-factor IC metric computation for external columns.
- `external-data-ai-mining`: Injects external data columns into the AI factor mining pipeline — `QlibDataProvider` loads them alongside Qlib fields, and `FactorCalculator`'s LLM prompt is updated to include external field names so the LLM can reference them when generating factor expressions.

### Modified Capabilities

None — existing capabilities unchanged.

## Impact

- **New file**: `quantaalpha/backtest/external_data.py` — shared loader
- **Modified**: `quantaalpha/backtest/custom_factor_calculator.py` — `get_qlib_stock_data()` injection
- **Modified**: `quantaalpha/backtest/runner.py` — `run()`, `_create_dataset()`, `_create_dataset_with_computed_factors()`
- **Modified**: `quantaalpha/backtest/factor_calculator.py` — `QlibDataProvider.get_stock_data()` injection, `_generate_factor_code()` prompt update
- **Modified**: `configs/backtest.yaml` — new `external_data` section
- No dependency changes, no API removals, no Qlib upgrades required
