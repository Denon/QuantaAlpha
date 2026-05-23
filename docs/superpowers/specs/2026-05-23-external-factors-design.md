# External Data Support for Factor Computation and Backtest

## Problem

Current factor computation uses only 6 Qlib price-volume fields (`$open, $high, $low, $close, $volume, $vwap`) plus derived `$return`. There is no way to:

1. Import pre-computed external factors (e.g., market cap signals) into backtest
2. Make new base data columns available for factor expression computation (both user-written and LLM-generated)
3. Expose new columns to the AI factor mining pipeline

## Design

Add a unified `external_data` section in `backtest.yaml`. A single file format (CSV or Parquet) provides both:

- **Base columns** — values loaded into the working DataFrame get `$` prefix, visible to expression parser and LLM (e.g., `$market_cap` becomes referencable in `$close / $market_cap`)
- **Standalone factors** — every external column is also merged as a feature column into the backtest dataset, so imported signals participate in model training even without expression referencing them

This works across both the backtest pipeline and the AI factor mining pipeline via a shared data loader.

### Data Format

```csv
date,instrument,market_cap,my_signal_1,my_signal_2
2023-01-03,SH600000,2.35e11,0.12,-0.05
2023-01-03,SH600001,1.12e11,0.08,0.03
```

- `date_column` and `instrument_column` are configurable per file
- All remaining columns are loaded as factors/data columns
- `instrument` values must match Qlib codes (e.g., `SH600000`)
- Index alignment via MultiIndex intersection handles date/instrument mismatches
- Missing values are handled by existing `Fillna` preprocessor

### Config Change

```yaml
# configs/backtest.yaml
external_data:
  files:
    - path: "data/external/market_data.csv"
      format: "csv"          # csv | parquet
      date_column: "date"
      instrument_column: "instrument"
```

### Code Changes

#### New file: `quantaalpha/backtest/external_data.py`

Shared utility, used by both pipelines:

- `load_external_data(config) -> Optional[pd.DataFrame]` — reads config, loads all files, returns DataFrame with MultiIndex `(datetime, instrument)` using original column names (no `$` prefix yet)
- Handles CSV/Parquet, dedup across files, missing file warnings

#### Modified: `quantaalpha/backtest/custom_factor_calculator.py`

- `get_qlib_stock_data()` — after loading Qlib fields, calls `load_external_data()` and appends external columns with `$` prefix
  ```python
  # After: df.columns = fields
  ext_df = load_external_data(config)
  if ext_df is not None:
      ext_df.columns = [f"${col}" for col in ext_df.columns]
      df = df.join(ext_df, how="left")
  ```

#### Modified: `quantaalpha/backtest/runner.py`

1. **`run()`** — after custom factor computation, load external data. If external data exists, pass it to both `_compute_per_factor_ic()` and `_create_dataset()`:
   ```python
   external_df = load_external_data(self.config)
   if external_df is not None:
       ext_per_factor_metrics = self._compute_per_factor_ic(external_df)
       per_factor_metrics.update(ext_per_factor_metrics)
   ```

2. **`_create_dataset()`** — new `external_df` parameter. If external data exists, force the computed-factors path even when there are no custom factors:
   ```python
   has_external = external_df is not None and not external_df.empty
   if has_computed_factors or has_external:
       return self._create_dataset_with_computed_factors(
           factor_expressions, computed_factors, external_df
       )
   ```

3. **`_create_dataset_with_computed_factors()`** — new `external_df` parameter, appends to `all_feature_dfs`

#### Modified: `quantaalpha/backtest/factor_calculator.py`

1. **`QlibDataProvider.get_stock_data()`** — same injection as `get_qlib_stock_data()`: load external columns, `$`-prefix them, join to returned DataFrame

2. **`FactorCalculator._generate_factor_code()`** — system prompt at line 268 updated to list available `$` fields dynamically from `self.data_df.columns` instead of hardcoding:
   ```python
   available_cols = [c for c in self.data_df.columns if c.startswith('$')]
   # "The input data is a pandas DataFrame with multi-index (datetime, instrument) 
   #  and columns: " + ", ".join(available_cols)
   ```

### Data Flow

```
                   external_data/files CSV/Parquet
                           │
                   load_external_data()  ←── shared utility
                      /            \
                     /              \
        get_qlib_stock_data()    QlibDataProvider.get_stock_data()
        (backtest pipeline)      (AI mining pipeline)
                │                       │
        $market_cap joins       $market_cap joins DataFrame,
        DataFrame, used in      listed in LLM prompt → LLM can
        expression eval         reference $market_cap in
                │               generated expressions
        BacktestRunner.run()
                │
        ├── _compute_per_factor_ic(external_df)
        └── _create_dataset_with_computed_factors(..., external_df)
                        │
                All features + label → Qlib DatasetH
```

### Edge Cases & Error Handling

| Case | Behavior |
|------|----------|
| `external_data` section absent or `files` empty | No-op, behavior unchanged |
| File not found | Log error, skip file, continue |
| Empty file | Log warning, skip |
| Missing date/instrument columns | Raise descriptive error |
| Instrument/date mismatch | Index intersection — only overlapping rows kept |
| Duplicate column names across files | Auto-dedup: keep first, log warning |
| Duplicate column with existing Qlib field | Qlib field takes precedence, external skipped |
| External data has no overlap with Qlib date range | Log warning, external data empty but no crash |
| Qlib-only mode + external data | Forced to computed-factors path so external data is included |
| No custom factors, only external data | Works — external data passed as features to DatasetH |

### Non-Goals

- No data validation of external factor values (trusted input)
- No automatic recalculation pipeline — files are static snapshots
- No live data fetching
- No frontend UI changes
- No changes to `data_template/generate.py` (depends on setting `FACTOR_COSTEER_SETTINGS.data_folder` — external data injection happens at runtime in FactorCalculator instead)

## Files Changed

| File | Change |
|------|--------|
| `quantaalpha/backtest/external_data.py` | **New** — shared data loader |
| `configs/backtest.yaml` | Add `external_data` section |
| `quantaalpha/backtest/custom_factor_calculator.py` | `get_qlib_stock_data()` injects external columns |
| `quantaalpha/backtest/runner.py` | `run()`, `_create_dataset()`, `_create_dataset_with_computed_factors()` — load + merge external data |
| `quantaalpha/backtest/factor_calculator.py` | `QlibDataProvider.get_stock_data()` injects external columns; LLM prompt updated with dynamic field list |
