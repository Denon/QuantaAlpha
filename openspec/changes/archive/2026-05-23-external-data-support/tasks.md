## 1. Shared external data loader

- [x] 1.1 Create `quantaalpha/backtest/external_data.py` with `load_external_data(config)` function
- [x] 1.2 Implement CSV loading with configurable date/instrument column names
- [x] 1.3 Implement Parquet loading support
- [x] 1.4 Implement multi-file concatenation with column dedup
- [x] 1.5 Handle edge cases: missing file (skip), empty file (skip), missing columns (raise), absent config section (return None)

## 2. Config update

- [x] 2.1 Add `external_data` section to `configs/backtest.yaml` with commented example

## 3. Backtest pipeline — data loading

- [x] 3.1 Modify `get_qlib_stock_data()` in `custom_factor_calculator.py` to call `load_external_data()` and `$`-prefix and join external columns

## 4. Backtest pipeline — runner

- [x] 4.1 Modify `run()` to load external data and pass to `_compute_per_factor_ic()` and `_create_dataset()`
- [x] 4.2 Modify `_create_dataset()` to accept `external_df` parameter and force computed-factors path when external data exists
- [x] 4.3 Modify `_create_dataset_with_computed_factors()` to accept `external_df` and append to `all_feature_dfs`

## 5. AI mining pipeline — data loading

- [x] 5.1 Modify `QlibDataProvider.get_stock_data()` in `factor_calculator.py` to call `load_external_data()` and `$`-prefix and join external columns

## 6. AI mining pipeline — LLM prompt

- [x] 6.1 Update `FactorCalculator._generate_factor_code()` system prompt to dynamically list `$`-prefixed columns from `self.data_df.columns` instead of hardcoded field list

## 7. Verification

- [x] 7.1 Create a minimal test CSV with `date, instrument, market_cap` columns
- [x] 7.2 Verify backtest pipeline handles external data (config, merge, metrics)
- [x] 7.3 Verify LLM prompt includes external field names when `data_df` has external columns

## 8. Column descriptions support

- [x] 8.1 Add `get_column_descriptions(config)` to `external_data.py` — reads optional `columns` mapping per file entry, returns `{col: description}` dict
- [x] 8.2 Add `columns` example to `configs/backtest.yaml` external_data section comment
- [x] 8.3 Add built-in descriptions for Qlib native fields ($open, $high, $low, $close, $volume, $vwap) in `_format_available_columns()`
- [x] 8.4 Enhance `_format_available_columns()` to accept `column_descriptions` dict and output a description list (multiline) instead of bare comma-separated field names
- [x] 8.5 Pass column descriptions through `QlibDataProvider.get_stock_data()` → `FactorCalculator` (constructor or setter)
- [x] 8.6 Verify LLM prompt renders descriptions when external data with `columns` config is loaded

## 9. External factor registration script

- [x] 9.1 Create `scripts/register_external_factor.py` CLI with `--name`, `--expression`, `--description`, `--formulation`, `--library` args
- [x] 9.2 Implement library JSON read → validate → add entry → write flow
- [x] 9.3 Implement conflict detection: error on duplicate name, `--force` to overwrite
- [x] 9.4 Set `factor_source: "external"`, `evolution_phase: "manual_import"`, auto-generated `factor_id`, `factor_metrics: null` in output entry
- [x] 9.5 Update library `metadata.last_updated` and `metadata.total_factors` after registration
- [x] 9.6 Verify registered factor appears in library and `FactorLoader` can read it correctly
