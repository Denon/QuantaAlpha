# Backtest V2 - 全功能回测工具

一个功能完整的量化回测工具，支持 Qlib 官方因子库和自定义因子库，并集成 LLM 自动计算复杂因子表达式。

## 功能特点

- 🎯 **多因子源支持**
  - Qlib 官方因子：Alpha158、Alpha158(20)、Alpha360
  - 自定义因子库（JSON 格式）
  - 组合模式：同时使用官方因子和自定义因子

- 🤖 **LLM 驱动的因子计算**
  - 自动识别 Qlib 不兼容的因子表达式
  - 使用 LLM 转换复杂表达式为可执行代码
  - 支持缓存，避免重复计算

- 📊 **完整回测流程**
  - LightGBM 模型训练
  - IC/ICIR/RankIC 指标计算
  - 组合策略回测（TopkDropout）
  - 年化收益、信息比率、最大回撤等指标

## 快速开始

### 1. 使用 Alpha158(20) 基础因子

```bash
python backtest_v2/run_backtest.py -c backtest_v2/config.yaml --factor-source alpha158_20
```

### 2. 使用 Alpha158 完整因子库

```bash
python backtest_v2/run_backtest.py -c backtest_v2/config.yaml --factor-source alpha158
```

### 3. 使用 Alpha360 扩展因子库

```bash
python backtest_v2/run_backtest.py -c backtest_v2/config.yaml --factor-source alpha360
```

### 4. 使用自定义因子库

```bash
python backtest_v2/run_backtest.py -c backtest_v2/config.yaml \
    --factor-source custom \
    --factor-json /path/to/factor_data/quality/high_quality_1.json
```

### 5. 组合使用官方因子和自定义因子

```bash
python backtest_v2/run_backtest.py -c backtest_v2/config.yaml \
    --factor-source combined \
    --factor-json /path/to/factor_data/quality/high_quality_1.json \
    --factor-json /path/to/factor_data/quality/high_quality_2.json
```

### 6. Walk-Forward Factor Selection (Walk-Forward回测)

Walk-forward模式按时间顺序分割数据为多个fold,每个fold只使用过去数据选择因子,然后在未来窗口上评估,消除前瞻偏差。

```bash
python -m quantaalpha.backtest.run_backtest \
  -c configs/backtest.yaml \
  --factor-source combined \
  --factor-json data/results/factor_library.json \
  --walk-forward
```

**工作原理:**
- 每个fold包含一个selection窗口(用于选择因子)和一个forward窗口(用于评估)
- 因子选择严格限制在`[selection_start, selection_end]`内,仅使用该区间的IC/ICIR指标
- `selection_lag_days`(默认2天)确保选择窗口结束日与决策日之间有缓冲,防止标签的前瞻引用泄漏
- 每个fold独立训练LightGBM并在forward窗口上运行回测

**输出文件** (保存在`experiment.output_dir`):
- `walk_forward_folds.json` — 每个fold的详情、选择因子及指标
- `walk_forward_selected_factors.csv` — 每个fold选中的因子列表
- `walk_forward_summary.json` — 跨fold聚合指标(各数值指标的均值)

**配置项:**
```yaml
walk_forward:
  enabled: false  # 设为true通过配置启用
  start_time: "2016-01-01"
  end_time: "2025-12-26"
  selection_window_months: 6
  forward_window_months: 6
  step_months: 6
  selection_lag_days: 2
  internal_valid_ratio: 0.2
  top_k: 20
  min_selection_days: 10
```

### 7. Dry Run 模式（仅加载因子）

```bash
python backtest_v2/run_backtest.py -c backtest_v2/config.yaml \
    --factor-source custom \
    --factor-json /path/to/factors.json \
    --dry-run -v
```

## 配置文件说明

配置文件 `config.yaml` 包含以下主要部分：

### 因子源配置
```yaml
factor_source:
  type: "alpha158_20"  # alpha158, alpha158_20, alpha360, custom, combined
  
  custom:
    json_files:
      - "/path/to/factors.json"
    quality_filter: null  # 可选：high_quality, medium_quality, low_quality
    max_factors: null  # 可选：最大因子数量
    use_llm_for_incompatible: true
```

### 数据配置
```yaml
data:
  provider_uri: "~/.qlib/qlib_data/cn_data"
  market: "csi300"  # csi300, csi500, all
  start_time: "2016-01-01"
  end_time: "2025-12-26"
```

### 数据集配置
```yaml
dataset:
  label: "Ref($close, -2) / Ref($close, -1) - 1"
  segments:
    train: ["2016-01-01", "2020-12-31"]
    valid: ["2021-01-01", "2021-12-31"]
    test:  ["2022-01-01", "2025-12-26"]
```

### 模型配置
```yaml
model:
  type: "lgb"
  params:
    loss: "mse"
    learning_rate: 0.2
    max_depth: 8
    num_leaves: 210
    # ... 更多参数
```

### 回测配置
```yaml
backtest:
  strategy:
    class: "TopkDropoutStrategy"
    kwargs:
      topk: 50
      n_drop: 5
  
  backtest:
    start_time: "2022-01-01"
    end_time: "2025-12-26"
    account: 100000000
    benchmark: "SH000905"
```

## 自定义因子 JSON 格式

自定义因子库使用 JSON 格式，结构如下：

```json
{
  "metadata": {
    "classification_type": "quality",
    "category": "high_quality",
    "total_factors": 60
  },
  "factors": {
    "factor_id_1": {
      "factor_id": "factor_id_1",
      "factor_name": "Risk_Adjusted_Momentum_20D",
      "factor_expression": "RANK(TS_MEAN($return, 20) / (TS_STD($return, 20) + 1e-8))",
      "factor_description": "A Sharpe-ratio-style momentum factor...",
      "quality": "high_quality",
      "backtest_metrics": {
        "IC": 0.0627,
        "ICIR": 0.639
      }
    }
  }
}
```

## 支持的因子表达式操作

### 截面函数
- `RANK(A)`: 截面排名
- `ZSCORE(A)`: 截面 Z-score
- `MEAN(A)`, `STD(A)`, `MAX(A)`, `MIN(A)`, `MEDIAN(A)`

### 时间序列函数
- `DELTA(A, n)`: n 期差分
- `DELAY(A, n)`: 延迟 n 期
- `TS_MEAN(A, n)`, `TS_STD(A, n)`, `TS_VAR(A, n)`
- `TS_MAX(A, n)`, `TS_MIN(A, n)`, `TS_SUM(A, n)`
- `TS_RANK(A, n)`, `TS_ZSCORE(A, n)`
- `TS_CORR(A, B, n)`, `TS_COVARIANCE(A, B, n)`

### 移动平均
- `SMA(A, n, m)`: 简单移动平均
- `EMA(A, n)`: 指数移动平均
- `WMA(A, n)`: 加权移动平均
- `DECAYLINEAR(A, d)`: 线性衰减平均

### 数学运算
- `LOG(A)`, `SQRT(A)`, `POW(A, n)`, `EXP(A)`
- `ABS(A)`, `SIGN(A)`, `INV(A)`, `FLOOR(A)`
- `MAX(A, B)`, `MIN(A, B)`, `PROD(A, n)`

### 条件与逻辑
- `COUNT(C, n)`: 条件计数
- `SUMIF(A, n, C)`: 条件求和
- `FILTER(A, C)`: 条件过滤
- `(C1)&&(C2)`, `(C1)||(C2)`: 逻辑运算
- `(C)?(A):(B)`: 条件表达式

### 回归函数
- `REGBETA(A, B, n)`: 回归系数
- `REGRESI(A, B, n)`: 回归残差
- `SEQUENCE(n)`: 生成序列

### 技术指标
- `RSI(A, n)`: 相对强弱指数
- `MACD(A, short, long)`: MACD
- `BB_MIDDLE(A, n)`, `BB_UPPER(A, n)`, `BB_LOWER(A, n)`: 布林带

## 输出结果

回测完成后，结果保存在 `backtest_v2_results/backtest_metrics.json`：

```json
{
  "experiment_name": "backtest_v2_experiment",
  "factor_source": "alpha158_20",
  "num_factors": 20,
  "metrics": {
    "IC": 0.0345,
    "ICIR": 0.456,
    "Rank IC": 0.0312,
    "Rank ICIR": 0.401,
    "annualized_return": 0.0892,
    "information_ratio": 1.234,
    "max_drawdown": -0.0876,
    "calmar_ratio": 1.018
  },
  "config": {
    "data_range": "2016-01-01 ~ 2025-12-26",
    "test_range": "2022-01-01 ~ 2025-12-26",
    "market": "csi300"
  },
  "elapsed_seconds": 156.78
}
```

## 目录结构

```
backtest_v2/
├── __init__.py          # 包初始化
├── config.yaml          # 配置文件
├── run_backtest.py      # 入口脚本
├── factor_loader.py     # 因子加载器
├── factor_calculator.py # 因子计算器（含 LLM 集成）
├── runner.py            # 回测执行器
└── README.md            # 使用说明
```

## 依赖项

- Python >= 3.8
- qlib
- pandas
- numpy
- pyyaml
- lightgbm
- openai (用于 LLM 因子计算)

## 常见问题

### Q: 如何禁用 LLM 因子计算？

在配置文件中设置：
```yaml
llm:
  enabled: false
```

### Q: 如何过滤低质量因子？

在配置文件中设置：
```yaml
factor_source:
  custom:
    quality_filter: "high_quality"
```

### Q: 如何限制因子数量？

在配置文件中设置：
```yaml
factor_source:
  custom:
    max_factors: 50
```

## 许可证

MIT License

