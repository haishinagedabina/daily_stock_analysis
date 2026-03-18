# 交易策略目录 / Trading Strategies

本目录存放 **自然语言策略文件**（YAML 格式）。系统启动时自动加载此目录下所有 `.yaml` 文件。

## 如何编写自定义策略

只需创建一个 `.yaml` 文件，用中文（或任意语言）描述你的交易策略即可，**无需编写任何代码**。

### 最简模板

```yaml
name: my_strategy          # 唯一标识（英文，下划线连接）
display_name: 我的策略      # 显示名称（中文）
description: 简短描述策略用途

instructions: |
  你的策略描述...
  用自然语言写出判断标准、入场条件、出场条件等。
  可以引用工具名称（如 get_daily_history、analyze_trend）来指导 AI 使用哪些数据。
```

### 完整模板（含量化筛选规则）

```yaml
name: my_strategy
display_name: 我的策略
description: 简短描述策略适用的市场场景

# 策略分类：trend（趋势）、pattern（形态）、reversal（反转）、framework（框架）
category: trend

# 关联的核心交易理念编号（1-7），可选
core_rules: [1, 2]

# 策略需要使用的工具列表，可选
required_tools:
  - get_daily_history
  - analyze_trend

# 量化筛选规则（可选）——用于全市场筛选
screening:
  filters:
    - field: breakout_ratio      # 因子字段名
      op: ">="                   # 操作符: >=, <=, >, <, ==, !=
      value: 0.995               # 阈值
    - field: ma5
      op: ">="
      value_ref: ma10            # 跨字段比较（ma5 >= ma10）
  scoring:
    - field: breakout_ratio      # 因子字段名
      weight: 40                 # 权重（0-100）
      bonus_above: 1.0           # 超过此值给额外加分
      bonus_multiplier: 1000     # 加分倍率
    - field: volume_ratio
      weight: 30
      cap: 5.0                   # 封顶值（防止极端值主导）
      invert: false              # true 时低值得高分（如缩量策略）

# 策略详细说明（自然语言，支持 Markdown 格式）
instructions: |
  **我的策略名称**

  判断标准：
  1. 条件一...
  2. 条件二...
```

### 可用因子字段

| 字段 | 说明 | 策略示例 |
|------|------|----------|
| `close` | 最新收盘价 | - |
| `ma5` / `ma10` / `ma20` / `ma60` | 移动均线 | 均线金叉、缩量回踩 |
| `volume_ratio` | 量比（当日/5日均量） | 放量突破、底部放量 |
| `breakout_ratio` | 突破比（收盘/N日高点） | 放量突破 |
| `trend_score` | 趋势评分（0-100） | 所有趋势类策略 |
| `liquidity_score` | 流动性评分（0-100） | 通用 |
| `pct_chg` | 当日涨跌幅（%） | 底部放量 |
| `pct_chg_5d` | 5日涨跌幅（%） | - |
| `pct_chg_20d` | 20日涨跌幅（%） | 底部放量 |
| `ma5_distance_pct` | 与MA5距离百分比 | 缩量回踩 |
| `amplitude` | 振幅（%） | - |
| `candle_pattern` | K线形态标识 | 一阳夹三阴 |
| `avg_amount` | 5日均成交额 | 流动性过滤 |
| `days_since_listed` | 上市天数 | 新股过滤 |
| `is_st` | 是否ST | ST过滤 |

### 核心交易理念参考

| 编号 | 理念 |
|------|------|
| 1 | 严进策略：乖离率 < 5% 才考虑入场 |
| 2 | 趋势交易：MA5 > MA10 > MA20 多头排列 |
| 3 | 效率优先：量能确认趋势有效性 |
| 4 | 买点偏好：优先回踩均线支撑 |
| 5 | 风险排查：利空新闻一票否决 |
| 6 | 量价配合：成交量验证价格运动 |
| 7 | 强势趋势股放宽：龙头股可适当放宽标准 |

## 自定义策略目录

除了本目录（内置策略），你还可以通过环境变量指定额外的自定义策略目录：

```env
AGENT_STRATEGY_DIR=./my_strategies
```

系统会同时加载内置策略和自定义策略。如果名称冲突，自定义策略覆盖内置策略。
