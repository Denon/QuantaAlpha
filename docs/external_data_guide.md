# External Data Import Guide

如何将外部数据（市值、估值比率、自定义信号等）导入因子计算和回测管线。

---

## 概述

默认情况下，因子计算只能使用 Qlib 提供的 6 个价量字段：

```
$open, $high, $low, $close, $volume, $vwap, $return (衍生)
```

引入外部数据后，你可以把任意指标（如市值、PE、ROE，甚至自己计算好的因子信号）导入系统，用于：

- **因子表达式计算** — 在表达式中像 `$open` 一样引用，例如 `$close / $market_cap`
- **AI 因子挖掘** — LLM 可以在生成因子表达式时使用这些新字段
- **直接作为回测特征** — 导入的列直接作为特征参与模型训练，不需要包装表达式

---

## 1. 文件格式

外部数据以 CSV 或 Parquet 格式提供。每一行是一个 (日期, 股票) 维度的数据点。

### 必须是长表格式（tall format），不是宽表

```
date,instrument,market_cap,pe_ttm,my_signal_1
2023-01-03,SH600000,2.35e11,5.2,0.12
2023-01-03,SH600001,1.12e11,8.1,-0.03
2023-01-03,SH600002,4.50e10,12.3,0.08
2023-01-04,SH600000,2.38e11,5.3,0.15
2023-01-04,SH600001,1.15e11,7.9,-0.01
2023-01-04,SH600002,4.55e10,12.1,0.11
...
```

### 字段要求

| 字段 | 要求 | 说明 |
|------|------|------|
| 日期列 | 必须 | 默认列名 `date` |
| 股票代码列 | 必须 | 默认列名 `instrument`，值必须与 Qlib 的代码一致（如 `SH600000`） |
| 数据列 | 至少一列 | 除日期和代码列外的所有列都被视为因子/数据 |

### 股票代码格式

代码必须与 Qlib 数据中的格式一致。标准格式：

| 交易所 | 前缀 | 例子 |
|--------|------|------|
| 上交所 | `SH` | `SH600000`, `SH688001` |
| 深交所 | `SZ` | `SZ000001`, `SZ002594` |

> 如果格式不匹配，外部数据会和 Qlib 数据的 index 做 intersection，不匹配的行会被静默丢弃。系统会在日志中打印重叠行数，如果看到 0 表示代码格式有问题。

### 日期格式

推荐 `YYYY-MM-DD`（如 `2023-01-03`）。实际上只要能自动推断出 `datetime64` 类型的格式都支持，包括：

```
2023-01-03
2023/01/03
20230103
2023-01-03 00:00:00
```

### 缺失值

允许数据有缺失日期或缺失股票。`pd.concat` 的 index intersection 只保留重叠部分，不重叠的自动对齐为 NaN，后续的 Fillna preprocessor 会填充。

---

## 2. 配置

编辑 `configs/backtest.yaml`，添加或取消注释 `external_data` 段：

```yaml
external_data:
  files:
    - path: "data/external/market_data.csv"
      format: "csv"
      date_column: "date"
      instrument_column: "instrument"
```

### 多文件合并

可以指定多个文件，所有文件的列会合并在一起：

```yaml
external_data:
  files:
    - path: "data/external/financial_ratios.csv"
      format: "csv"
      date_column: "date"
      instrument_column: "instrument"
    - path: "data/external/my_signals.parquet"
      format: "parquet"
      date_column: "date"
      instrument_column: "instrument"
```

- 多个文件用 `pd.concat(axis=1)` 按其 index 对齐
- 同名列按文件顺序保留第一个，后续重复列被丢弃（有 warning log）
- 支持混合 CSV 和 Parquet

### 列描述（推荐）

可以为每个外部列添加描述，LLM 在生成因子表达式时会看到这些描述，从而更好地理解数据含义：

```yaml
external_data:
  files:
    - path: "data/external/market_data.csv"
      columns:               # 可选：列描述，增强 LLM 理解
        market_cap: "Total market capitalization (CNY), measures company size"
        pe_ttm: "Trailing P/E ratio, lower values indicate lower valuation"
```

不写 `columns` 的字段仍然可用，只是 LLM 只看到裸字段名。

### 字段配置说明

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `path` | — (必须) | 文件路径，支持 `~` |
| `format` | `csv` | `csv` 或 `parquet` |
| `date_column` | `date` | 日期列在文件中的列名 |
| `instrument_column` | `instrument` | 股票代码列在文件中的列名 |
| `columns` | — (可选) | 列名→描述 映射，供 LLM 理解字段含义 |

---

## 3. 怎么在两个 Pipeline 中使用

### 3.1 回测管线（Backtest Pipeline）

外部数据在回测中**自动生效**，分两个层次：

**层次 1：作为基础数据列（参与表达式计算）**

所有外部列被加上 `$` 前缀注入到工作 DataFrame：
- 文件中叫 `market_cap` → 表达式中用 `$market_cap`
- 文件中叫 `pe_ttm` → 表达式中用 `$pe_ttm`

可以像原生字段一样在因子表达式中引用：

```
RANK($close / $market_cap)           # 市值倒数排序
ZSCORE($pe_ttm)                      # PE z-score
TS_MEAN($close / $market_cap, 20)    # 20日均值
```

表达式计算自动走 `CustomFactorCalculator`，`$market_cap` 已经存在于 DataFrame 中。

**层次 2：作为独立因子（直接参与训练）**

外部列的原始值（不加 `$` 前缀）作为**独立因子列**并入回测数据集，和自定义表达式计算的结果、Qlib 内置因子（如 alpha158）一起参与模型训练。

**验证效果：**

运行回测时，终端输出会显示：

```
[2/4] Computed custom factors: 20
  Computed per-factor IC metrics: 20/20
  External data metrics: 3/3 columns
[3/4] Dataset created
```

- `3/3 columns` 表示外部数据中的 3 列都计算了 per-factor IC 指标
- 最终结果 JSON 的 `per_factor_metrics` 中包含这些列的 IC、Rank IC 等

**计数器：** 最终输出的因子数量 = `qlib因子数 + 自定义表达式因子数 + 外部数据列数`

### 3.2 AI 因子挖掘管线（AI Mining Pipeline）

外部数据**同时自动生效**于 AI 管线：

1. `QlibDataProvider.get_stock_data()` 加载数据时注入外部列
2. `FactorCalculator` 的 LLM prompt 动态列出所有可用字段及其描述

例如，LLM 看到的 prompt 片段（配置了 `columns` 描述时）：

```
Available data columns (use $variable format in expressions):
  $open: Opening price
  $high: High price
  $low: Low price
  $close: Closing price
  $volume: Trading volume
  $vwap: Volume-weighted average price
  $market_cap: Total market capitalization (CNY), measures company size
  $pe_ttm: Trailing P/E ratio, lower values indicate lower valuation
```

LLM 在生成因子表达式时就能理解每个字段的含义。如果不配置 `columns`，外部字段仅列出字段名（无描述），但 Qlib 原生字段始终附带英文描述。

> 注意：AI 管线数据注入是运行时行为，不修改 `data_template/generate.py` 生成的文件。

---

## 4. 完整操作流程

### 步骤 1：准备外部数据

用你习惯的工具（Python、SQL、Excel 导出）生成外部数据文件。

**Python 示例：**

```python
import pandas as pd
import numpy as np

# 假设你有股票列表和日期范围
instruments = ['SH600000', 'SH600001', 'SH600002']
dates = pd.date_range('2023-01-03', '2025-12-31', freq='B')

rows = []
for inst in instruments:
    for d in dates:
        rows.append({
            'date': d.strftime('%Y-%m-%d'),
            'instrument': inst,
            'market_cap': np.random.uniform(1e10, 5e11),  # 你的真实数据
            'pe_ttm': np.random.uniform(5, 30),
        })

df = pd.DataFrame(rows)
df.to_csv('data/external/market_data.csv', index=False)
print(f"Saved {len(df)} rows")
```

### 步骤 2：放到项目目录

```bash
cp your_data.csv data/external/market_data.csv
```

### 步骤 3：配置

编辑 `configs/backtest.yaml`，取消注释 `external_data` 段，填上路径：

```yaml
external_data:
  files:
    - path: "data/external/market_data.csv"
      format: "csv"
      date_column: "date"
      instrument_column: "instrument"
```

### 步骤 4：运行回测验证

```bash
conda run -n rdagent python quantaalpha/backtest/run_backtest.py \
  -c configs/backtest.yaml \
  --factor-source custom \
  --factor-json data/factorlib/all_factors_library.json
```

观察输出中的 `External data metrics: X/X` 行，确认所有外部列都成功加载并参与了回测。

### 步骤 5：编写使用新字段的因子表达式

在 `data/factorlib/all_factors_library.json` 中添加利用外部列的因子：

```json
{
  "factor_name": "value_factor",
  "factor_expression": "RANK(-1 * (($close / $market_cap) * $pe_ttm))",
  "factor_description": "市值倒数加权PE的综合值因子"
}
```

运行时会自动从表达式引用 `$market_cap` 和 `$pe_ttm`。



---

## 5. 将外部因子注册到因子库

如果外部数据是预计算好的因子（不只是基础字段），可以注册到 `all_factors_library.json`。这样 AI 挖掘管线在后续轮次中能看到这些因子的完整语义（名称、表达式、描述、公式），从而在其基础上继续推导。

### 步骤 1：注册因子

```bash
python scripts/register_external_factor.py \
  --name "market_cap_factor" \
  --expression "$market_cap" \
  --description "Total market capitalization. Measures company size. Larger firms typically have lower volatility and higher liquidity." \
  --formulation "MC_i = P_i \times S_i" \
  --library data/factorlib/all_factors_library.json
```

### 步骤 2：验证注册结果

```bash
python -c "
import json
with open('data/factorlib/all_factors_library.json') as f:
    lib = json.load(f)
for fid, finfo in lib['factors'].items():
    if finfo.get('factor_name') == 'market_cap_factor':
        print(finfo['factor_description'])
"
```

### 步骤 3：回填 IC 指标（可选）

注册后 `factor_metrics` 为 null，运行 backfill 脚本回填：

```bash
python scripts/backfill_factor_metrics.py \
  --library data/factorlib/all_factors_library.json \
  --config configs/backtest.yaml
```

### 脚本参数

| 参数 | 说明 |
|------|------|
| `--name` | 因子名称（必须唯一，除非用 `--force`） |
| `--expression` | 因子表达式，如 `$market_cap` |
| `--description` | 人类可读描述，LLM 推理时使用 |
| `--formulation` | LaTeX 或纯文本公式 |
| `--library` | 因子库路径，默认 `data/factorlib/all_factors_library.json` |
| `--force` | 覆盖同名已有因子 |

### CSV 与因子库的配合关系

```
CSV 文件            →  提供数值（DataFrame 列）
columns 配置        →  提供列级语义（LLM 知道每列的含义）
register 脚本       →  提供因子级语义（LLM 知道因子的逻辑、公式、推导思路）
```

三者结合，LLM 在 AI 挖掘管线中获得的数据理解能力接近原生字段：

```
已注册因子的 factor_description 出现在 LLM 上下文中：
"Existing factor: market_cap_factor — Total market capitalization.
 Measures company size. Larger firms typically have lower volatility."
```

---

## 6. 常见问题

### Q: 外部数据需要覆盖所有日期和所有股票吗？

不需要。系统通过 index intersection 自动对齐。只有同时存在于 Qlib 数据和外部文件中的 (日期, 股票) 组合才会参与计算。只覆盖部分时间段或部分股票是完全可以的。

### Q: 外部数据能和 alpha158 内置因子一起用吗？

可以。举个例子，你想用 ``alpha158`` 的因子 + 你外部文件里的 3 列信号：

```yaml
factor_source:
  type: "alpha158"

external_data:
  files:
    - path: "data/external/my_signals.csv"
```

最终数据集 = alpha158 的因子 + 你的外部信号列。

### Q: 如果外部列和计算出来的表达式因子同名怎么办？

计算出来的因子优先，外部列被丢弃（有 warning log）。优先顺序是：**Qlib 表达式因子 > 外部数据列**。

### Q: Parquet 和 CSV 哪个更好？

数据量大（> 10万行）推荐用 Parquet：
- 列式存储，压缩率更高
- 读取速度比 CSV 快 5-10x
- 保留列类型信息

### Q: 外部数据如何更新？

目前外部数据文件是静态快照。要更新数据，替换文件后重新运行回测即可。系统不会自动拉取或计算外部数据。

### Q: 可以添加日频之外的粒度吗（如分钟级）？

目前两个 pipeline 都是日频的（`freq='day'`）。如果你有更高频率的数据，需要先重采样到日频，或者在更底层修改 Qlib 的数据加载逻辑——这超出了外部数据导入的范围。

### Q: 在 AI 挖掘中 LLM 会优先使用外部字段吗？

不会优先。LLM 看到的是一个平铺的可用字段列表，它根据因子描述自行决定用哪些字段。如果你的描述中提到 "利用市值信息" ，LLM 自然会引用 `$market_cap`。
