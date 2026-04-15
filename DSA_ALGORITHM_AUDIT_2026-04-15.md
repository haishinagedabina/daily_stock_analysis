# DSA 选股算法深度审计报告

> 审计日期：2026-04-15
> 数据来源：`stock_analysis.db`（7次screening run，80条候选记录，72只不同股票）
> 代码版本：`E:\daily_stock_analysis\src\services\` + `strategies/*.yaml`

---

## 一、算法体系概览

当前DSA选股系统由 **12个策略YAML** + **StrategyScreeningEngine** + **AI二次审核** 组成：

| 策略 | system_role | 实际命中次数 | 占比 |
|------|------------|-------------|------|
| volume_breakout | confirm | **43** | 31.6% |
| bottom_divergence_double_breakout | entry_core | **29** | 21.3% |
| ma100_60min_combined | entry_core | **19** | 14.0% |
| shrink_pullback | entry_core | **17** | 12.5% |
| ma100_low123_combined | entry_core | **15** | 11.0% |
| bottom_volume | observation | **5** | 3.7% |
| trendline_breakout | confirm | **5** | 3.7% |
| one_yang_three_yin | bonus_signal | **2** | 1.5% |
| extreme_strength_combo | stock_pool | **0** | 0% |
| dragon_head | stock_pool | **0** | 0% |
| bull_trend | stock_pool | **0** | 0% |
| gap_limitup_breakout | entry_core | **0** | 0% |

---

## 二、已发现缺陷（含证据）

### 缺陷1：volume_breakout 策略产出大量"追高型"候选 ⚠️⚠️⚠️

**严重程度：高**

**证据：**
- volume_breakout 命中 43 次，占总命中的 31.6%，是所有策略中最高的
- 在所有 ma5_distance_pct > 10% 的候选中，**28条中有23条**命中了 volume_breakout
- 典型案例：
  - 派诺科技(920375)：ma5距离29.2%，涨幅22%，score=94.2 — **第一高分**
  - 腾远钴业(301219)：ma5距离20.2%，涨停20%
  - 利扬芯片(688135)：ma5距离20.8%，涨停20%
  - 中恒电气(002364)：ma5距离19.9%，涨停10%

**根因分析：**
```yaml
# volume_breakout.yaml 的 filters：
- field: breakout_ratio  # >= 0.995
- field: volume_ratio    # >= 2.0
- field: trend_score     # >= 40
- field: close_strength  # >= 0.5
```
**没有任何乖离率过滤条件**。只要放量+突破+趋势好+收盘强势，就能入选。而涨停板天然满足这4个条件（breakout_ratio高、放量、趋势好、涨停收盘=close_strength=1.0），导致大量涨停板被选入，但涨停板次日买入的实操性极低。

**打分机制进一步放大问题：**
```yaml
scoring:
  - field: breakout_ratio
    weight: 40
    bonus_above: 1.0
    bonus_multiplier: 1000  # breakout_ratio每超过1.0一个点，加1000分！
```
兴图新科(688081)：breakout_ratio=1.15，单项得分 = 40 + (0.15 × 1000) = **190分**。一个 volume_breakout 策略就能拿到 188.4 的总分，远超其他策略。

---

### 缺陷2：大阴线当日仍被选入候选池 ⚠️⚠️

**严重程度：中高**

**证据：**
- 中嘉博创(000889)在2026-04-13的run中：
  - `pct_chg = -9.88%`（近跌停大阴线）
  - `close_strength = 0.0`（收在当日最低）
  - `candle_pattern = big_yin`
  - 却仍以 score=67.07 入选第4名，命中3个策略

**根因分析：**
- `bottom_divergence_double_breakout` 策略的 filter 只检查 `bottom_divergence_double_breakout == true`，不看当日K线形态
- `ma100_60min_combined` 策略只检查 `ma100_60min_confirmed == true`，不看当日涨跌
- `ma100_low123_combined` 同理
- **没有任何策略在filter层面要求当日不能是大阴线**

底背离确认发生在前几天，信号本身可能有效，但当信号确认日价格已跑远、且在选股当天出现大阴线回落时，系统未识别出"信号已过期 + 大阴线 = 不应推荐"的组合。

---

### 缺陷3：extreme_strength_combo/dragon_head/bull_trend 三个策略从未命中 ⚠️⚠️

**严重程度：中**

**证据：**
- 7次run，80条候选，这3个策略命中次数均为0
- extreme_strength_combo 是 `stock_pool` 角色，要求 `is_hot_theme_stock == true`
- dragon_head 和 bull_trend 没有定义 `screening` 字段

**根因分析：**
1. **extreme_strength_combo**：需要 `is_hot_theme_stock == true`，这个字段依赖 `HotThemeScreener` 的外部题材输入。从数据库看，所有候选的 `is_hot_theme_stock` 都是 false 或不存在。说明**题材匹配链路断裂** — 外部热点题材到因子快照的映射管道未通。
2. **dragon_head** 和 **bull_trend**：YAML 中没有 `screening:` 字段定义，`build_rules_from_skills()` 会跳过没有 screening dict 的策略。这两个策略只有 `instructions`，**本质上是给AI分析用的提示词，不是量化筛选规则**，永远不会在 screening 引擎中被执行。
3. **gap_limitup_breakout** 也从未命中：YAML中定义了filter，但用了 `or:` 语法（`gap_breakaway == true or: limit_up_breakout == true`），而 `_parse_filter_node()` 不支持这个 `or:` 语法，导致该条件**被静默忽略**，实际只检查 `above_ma100 == true` + `gap_breakaway == true`。大量涨停股不满足 gap_breakaway 但满足 limit_up_breakout，被误拒。

---

### 缺陷4：评分体系缺乏归一化，策略间分数不可比 ⚠️⚠️

**严重程度：中**

**证据：**
- 同一只股票在不同策略的得分差异巨大：
  - 兴图新科(688081)：volume_breakout=**188.4**分（单策略）
  - 生益电子(688183)：bottom_divergence=52.8，ma100_60min=73.93，ma100_low123=77.33（多策略叠加=204.06）
- 最终排名用的是所有策略分数之和：`final_score = sum(strategy_scores.values())`
- 这导致**匹配策略越多的股票天然排名越高**，而不是"信号质量最好"的排名高

**具体问题：**
1. volume_breakout 的 `bonus_multiplier: 1000` 使得一个策略就能拿到100+分，而其他策略的满分也就40-45分左右
2. 策略叠加是简单求和，没有权重衰减。一只股票如果恰好同时满足5个策略的最低门槛（每个40分），总分200分，轻松碾压一只只满足1个策略但该策略极度完美的股票（100分）
3. entry_core（买入信号）和 confirm（确认信号）和 bonus_signal（加分信号）在求和时**权重完全相同**，system_role 字段形同虚设

---

### 缺陷5：选股时效性控制不足，过期信号反复入选 ⚠️

**严重程度：中**

**证据：**
- 利扬芯片(688135)：底背离A点2025-11-24 → B点2025-12-17，双突破确认于2026-01-07/01-09，但在 2026-04-13 的run中仍被选入（信号发生**3个月前**）
- 中嘉博创(000889)：底背离突破确认于2026-04-09/10，但到04-13出现大阴线回落时仍被选入
- 兴图新科(688081)：`ma100_breakout_days = 163`（站上MA100已163天），完全不是"刚突破"

**根因分析：**
- `bottom_divergence_double_breakout` 策略只检查 `== true`，**没有时效性过滤**（比如"突破确认必须在最近N天内"）
- `ma100_60min_combined` 有 freshness 控制（≤5天），但 `bottom_divergence` 没有
- `volume_breakout` 同样没有时效性检查，只要当天满足条件就入选，但 breakout_ratio=0.995 本质是"收盘价接近20日最高"，不是"刚突破"

---

### 缺陷6：shrink_pullback（缩量回踩）缺少关键的"企稳确认"条件 ⚠️

**严重程度：低中**

**证据：**
- shrink_pullback 命中17次，是第4高频策略
- 但其 filter 只检查：MA5>=MA10>=MA20 + volume_ratio<=0.8 + ma5_distance<=2% + pct_chg>0
- **没有检查价格是否真的触碰了MA5/MA10支撑位**。一只股票只要在上升趋势中有任何一天缩量微涨、且距离MA5不远，就会命中
- 这意味着上涨途中的正常波动也会触发"缩量回踩"信号

---

### 缺陷7：AI二审覆盖率极低，大量候选"裸奔" ⚠️

**严重程度：低中**

**证据：**
- 80条候选中，只有**8条**经过AI审核（`selected_for_ai = 1`），覆盖率仅 10%
- AI审核结果：2条 focus，2条 reject，3条 stand_aside，1条 watch — **没有一条给出 buy 建议**
- 最大的run（2026-04-14第一次，50个候选），只有8个送审，42个直接输出无AI保护
- `ai_top_k` 配置为 2 或 8，限制了送审数量

**影响：**
- 规则层面的追高、过期信号等问题本可被AI二审拦截，但大部分候选根本没过AI这一关
- 从AI审核结果看，被审核的8个候选中有5个被判为 stand_aside 或 reject（都是因为乖离率太高），说明AI确实能发现追高问题，但它看不到那42个未送审的候选

---

## 三、缺陷严重程度排序

| 排名 | 缺陷 | 影响 | 修复难度 |
|------|------|------|----------|
| 1 | volume_breakout 缺乏乖离率过滤 + bonus_multiplier过高 | 大量追高型候选污染结果 | 低（加filter + 调参数） |
| 2 | 大阴线不被过滤 | 推荐当日暴跌股 | 低（加common_filter） |
| 3 | 3+1个策略从未命中（含or语法bug） | 33%策略失效 | 中（修bug + 补screening定义） |
| 4 | 评分无归一化，策略间不可比 | 排名逻辑失真 | 中（需设计归一化方案） |
| 5 | 底背离等信号缺乏时效性控制 | 过期信号反复推荐 | 低（加天数filter） |
| 6 | shrink_pullback 缺少支撑位触碰确认 | 假信号偏多 | 中（需改因子计算） |
| 7 | AI二审覆盖率过低 | 规则层缺陷无兜底 | 低（调 ai_top_k 配置） |

---

## 四、数据支撑汇总

- 追高候选（ma5距离>10%）：**28条 / 80条 = 35%**
- 涨停入选：**27条 / 80条 = 34%**（涨停板次日实操买入概率极低）
- 策略从未命中：**4个 / 12个 = 33%**
- AI审核覆盖：**8条 / 80条 = 10%**
- 大阴线入选：**至少1条**（可能被低估，仅统计了candle_pattern=big_yin）

---

*报告生成于 2026-04-15 10:14 CST*
