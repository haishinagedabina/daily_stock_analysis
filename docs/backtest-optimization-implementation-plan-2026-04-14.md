# 回测模块优化实施方案

> 日期：2026-04-14  
> 状态：待实施  
> 优先级：P0 → P1 → P2 分三阶段

---

## 一、现状问题

### 1.1 核心矛盾

回测模块的目的是验证"选股及买卖点预测的准确性"，但当前实现偏向统计报表，没有直接回答以下关键问题：

| 应该回答的问题 | 现状 |
|---------------|------|
| 我的系统整体行不行？ | ❌ 没有一眼可见的综合评分 |
| 哪个策略好用、哪个该关？ | ❌ setup_type 分组混在大表格里，没有盈亏比 |
| trade_stage 判断准不准？ | ❌ 只做了分组平均收益，没算判断准确率 |
| 入场成熟度分级有效吗？ | ⚠️ RankingEffectiveness 算了但前端不展示 |
| 入场时机精确吗？ | ❌ MAE 数据有但没有按策略分析呈现 |
| 止盈止损执行情况？ | ❌ plan_success 后端算了前端不展示 |

### 1.2 前端页面问题

- **信息平铺无层次**：运行概览 → 分组汇总 → 候选列表三段式，没有信息优先级
- **分组汇总表混杂**：overall / signal_family / setup_type / market_regime / combo 几十行混在一个表，用户无法快速定位
- **候选列表是流水账**：10 个字段平铺，入场和观察信号混在一起，重点不突出
- **缺失关键交易指标**：盈亏比、最大连续亏损、平均持仓天数、止盈止损执行率均未展示

### 1.3 后端计算缺失

`GroupSummaryAggregator.aggregate_group()` 当前只计算：
- avg_return_pct / median_return_pct / win_rate_pct
- avg_mae / avg_mfe / avg_drawdown
- p25 / p75 / extreme_sample_ratio / time_bucket_stability

缺失：
- profit_factor（盈亏比）
- avg_holding_days（平均持仓天数）
- max_consecutive_losses（最大连续亏损次数）
- plan_execution_rate（止盈止损执行成功率）
- stage_accuracy_rate（交易阶段判断准确率）

---

## 二、目标架构

### 2.1 页面信息层级

重构为 4 层，每层回答一个明确问题：

```
┌─────────────────────────────────────────────────────────────┐
│ 第1层：系统体检卡（Hero Section）                             │
│ "我的系统行不行？"  ← 30秒看完结论                             │
├─────────────────────────────────────────────────────────────┤
│ 第2层：策略拆解                                               │
│ "哪个策略好用，哪个不行？"  ← 按 setup_type 对比              │
├─────────────────────────────────────────────────────────────┤
│ 第3层：判断验证面板                                            │
│ "我的分级/标签判断准吗？"  ← 3个子面板                        │
│  ├── 3A. 交易阶段判断准确率                                    │
│  ├── 3B. 入场成熟度分级验证                                    │
│  └── 3C. MAE入场精度分析                                      │
├─────────────────────────────────────────────────────────────┤
│ 第4层：个股明细（可折叠）                                      │
│ "具体哪只股对了/错了？"  ← 分Tab + 展开行                     │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 系统体检卡指标定义

页面顶部 6 个 KPI 卡片：

| 指标 | 定义 | 评判标准 |
|------|------|---------|
| **总胜率** | entry 信号中 outcome="win" 的占比 | >55% 优, 45-55% 中, <45% 差 |
| **盈亏比** | sum(正收益) / abs(sum(负收益)) | >1.5 优, 1.0-1.5 中, <1.0 差 |
| **平均收益** | entry 信号 forward_return_5d 均值 | >2% 优, 0-2% 中, <0% 差 |
| **最大回撤** | entry 信号 avg_drawdown | >-3% 优, -3~-5% 中, <-5% 差 |
| **信号质量** | entry 信号 avg signal_quality_score | >0.6 优, 0.4-0.6 中, <0.4 差 |
| **综合评分** | 加权综合 → A/B/C/D 等级 | 见 §3.5 评分算法 |

### 2.3 策略对比表字段

按 setup_type 维度展示，每行一个策略：

```
策略名 | 样本数 | 胜率 | 盈亏比 | 平均5日收益 | 平均MAE | 信号质量 | 止盈执行率 | 评级
```

评级规则：
- 🟢 优：胜率>55% 且 盈亏比>1.5
- 🟡 中：胜率>45% 或 盈亏比>1.0
- 🔴 差：胜率<45% 且 盈亏比<1.0

### 2.4 判断验证面板

**3A. 交易阶段判断准确率**

| 字段 | 来源 |
|------|------|
| 阶段名称 | snapshot_trade_stage |
| 样本数 | 该阶段候选数 |
| 判断准确率 | entry: forward_return_5d > 0 为正确; observation: stage_success = True 为正确 |
| 平均收益 | 该阶段 avg forward_return_5d |

**3B. 入场成熟度分级验证**

| 字段 | 来源 |
|------|------|
| 等级 | snapshot_entry_maturity (HIGH/MEDIUM/LOW) |
| 胜率 | 该等级 win_rate |
| 平均收益 | 该等级 avg_return |
| 分级一致性 | HIGH > MEDIUM > LOW 是否成立（来自 RankingEffectivenessCalculator） |

**3C. MAE 入场精度分析**

| 字段 | 来源 |
|------|------|
| 策略 | snapshot_setup_type |
| 平均MAE | 该策略 entry 信号的 avg(mae) |
| MAE < -2% 占比 | mae < -2 的样本占比 |
| 入场偏早率 | MAE < -3% 的占比（入场后回撤超3%认为偏早） |

### 2.5 个股明细优化

**分 Tab 展示：**

Tab 1：入场信号
```
代码 | 名称 | 日期 | 策略(setup_type) | 入场价 | 5日收益 | 10日收益 | MAE | MFE | 盈亏 | 止盈止损 | 信号质量
```

Tab 2：观察信号
```
代码 | 名称 | 日期 | 阶段 | 假设入场价 | 规避风险% | 错过收益% | 判断结果 | 结论
```

**展开行（点击行展开详情）：**

展示 `factor_snapshot_json` 和 `trade_plan_json` 的结构化内容：
- 因子快照：MA100状态、底背离状态、趋势线突破、缺口检测等
- 交易计划：止盈目标 → 是否触达、止损线 → 是否触发、计划执行结果

---

## 三、后端改动详情

### 3.1 GroupSummary 表新增字段

文件：`src/backtest/models/backtest_models.py`

```python
# FiveLayerBacktestGroupSummary 新增列
profit_factor = Column(Float)              # 盈亏比
avg_holding_days = Column(Float)           # 平均持仓天数
max_consecutive_losses = Column(Integer)   # 最大连续亏损次数
plan_execution_rate = Column(Float)        # 止盈止损成功率 (0-1)
stage_accuracy_rate = Column(Float)        # 交易阶段判断准确率 (0-1)
system_grade = Column(String(4))           # 综合评分 A+/A/B+/B/C/D
```

需要同步更新：
- `to_dict()` 方法
- `summary_repo.py` 的 `upsert_summary()` 参数

### 3.2 aggregate_group() 新增计算

文件：`src/backtest/aggregators/group_summary_aggregator.py`

在 `aggregate_group()` 函数中新增：

```python
# --- 盈亏比 ---
positive_returns = [r for r in returns if r > 0]
negative_returns = [r for r in returns if r < 0]
total_positive = sum(positive_returns) if positive_returns else 0
total_negative = abs(sum(negative_returns)) if negative_returns else 0
profit_factor = round(total_positive / total_negative, 4) if total_negative > 0 else None

# --- 平均持仓天数 ---
holding_vals = [e.holding_days for e in valid if e.holding_days is not None and e.holding_days > 0]
avg_holding_days = round(statistics.mean(holding_vals), 2) if holding_vals else None

# --- 最大连续亏损 ---
sorted_evals = sorted(
    [e for e in valid if e.trade_date is not None and e.outcome is not None],
    key=lambda e: (e.trade_date, e.code),
)
max_consecutive_losses = 0
current_streak = 0
for e in sorted_evals:
    if e.outcome == "loss":
        current_streak += 1
        max_consecutive_losses = max(max_consecutive_losses, current_streak)
    else:
        current_streak = 0

# --- 止盈止损执行率 ---
plan_evals = [e for e in valid if e.plan_success is not None]
plan_execution_rate = (
    round(sum(1 for e in plan_evals if e.plan_success) / len(plan_evals), 4)
    if plan_evals else None
)

# --- 交易阶段判断准确率 ---
stage_correct = 0
stage_total = 0
for e in valid:
    if e.signal_family == "entry" and e.forward_return_5d is not None:
        stage_total += 1
        if e.forward_return_5d > 0:
            stage_correct += 1
    elif e.signal_family == "observation" and e.stage_success is not None:
        stage_total += 1
        if e.stage_success:
            stage_correct += 1
stage_accuracy_rate = round(stage_correct / stage_total, 4) if stage_total > 0 else None
```

### 3.3 新建 SystemGrader

文件：`src/backtest/aggregators/system_grader.py`（新建）

```python
class SystemGrader:
    """综合评分算法，输出 A+/A/B+/B/C/D"""

    @staticmethod
    def grade(
        win_rate_pct: float | None,
        profit_factor: float | None,
        time_bucket_stability: float | None,
        sample_count: int,
    ) -> str:
        if sample_count < 10:
            return "N/A"

        score = 0.0

        # 胜率得分 (0-40分)
        if win_rate_pct is not None:
            if win_rate_pct >= 60: score += 40
            elif win_rate_pct >= 55: score += 35
            elif win_rate_pct >= 50: score += 25
            elif win_rate_pct >= 45: score += 15
            else: score += 5

        # 盈亏比得分 (0-40分)
        if profit_factor is not None:
            if profit_factor >= 2.0: score += 40
            elif profit_factor >= 1.5: score += 35
            elif profit_factor >= 1.2: score += 25
            elif profit_factor >= 1.0: score += 15
            else: score += 5

        # 稳定性得分 (0-20分)
        if time_bucket_stability is not None:
            if time_bucket_stability <= 0.08: score += 20
            elif time_bucket_stability <= 0.12: score += 15
            elif time_bucket_stability <= 0.15: score += 10
            else: score += 5

        # 映射等级
        if score >= 90: return "A+"
        if score >= 80: return "A"
        if score >= 70: return "B+"
        if score >= 55: return "B"
        if score >= 40: return "C"
        return "D"
```

### 3.4 Evaluation to_dict() 补充字段

文件：`src/backtest/models/backtest_models.py`

`FiveLayerBacktestEvaluation.to_dict()` 补充暴露：

```python
"factor_snapshot_json": self.factor_snapshot_json,
"trade_plan_json": self.trade_plan_json,
"signal_type": self.signal_type,
"evaluation_mode": self.evaluation_mode,
"snapshot_source": self.snapshot_source,
"replayed": self.replayed,
```

### 3.5 API schema 新增字段

文件：`api/v1/schemas/five_layer_backtest.py`

**FiveLayerGroupSummaryItem 新增：**

```python
profit_factor: Optional[float] = None
avg_holding_days: Optional[float] = None
max_consecutive_losses: Optional[int] = None
plan_execution_rate: Optional[float] = None
stage_accuracy_rate: Optional[float] = None
system_grade: Optional[str] = None
```

**FiveLayerEvaluationItem 新增：**

```python
factor_snapshot_json: Optional[str] = None
trade_plan_json: Optional[str] = None
signal_type: Optional[str] = None
```

### 3.6 新增 API 端点：排名有效性

文件：`api/v1/endpoints/five_layer_backtest.py`

```
GET /runs/{backtest_run_id}/ranking-effectiveness
```

返回 `RankingEffectivenessReport` 的 JSON 序列化，包含：
- comparisons: 各维度层级对比列表
- overall_effectiveness_ratio
- top_k_hit_rate
- excess_return_pct
- ranking_consistency

---

## 四、前端改动详情

### 4.1 文件清单

| 文件 | 改动 |
|------|------|
| `types/backtest.ts` | 新增字段类型定义 |
| `api/backtest.ts` | 新增 getRankingEffectiveness API 调用 |
| `pages/BacktestPage.tsx` | 整体重构为4层布局 |
| `components/backtest/SystemScorecard.tsx` | **新建** - 第1层体检卡组件 |
| `components/backtest/StrategyComparison.tsx` | **新建** - 第2层策略对比组件 |
| `components/backtest/JudgmentValidation.tsx` | **新建** - 第3层判断验证组件 |
| `components/backtest/EvaluationDetail.tsx` | **新建** - 第4层个股明细组件（含展开行） |

### 4.2 第1层组件：SystemScorecard

```tsx
// 6个KPI卡片横排
// 每个卡片: 指标名 + 数值 + 进度条 + 颜色标识(绿/黄/红)
// 数据来源: summaries 中 group_type="overall" 的记录

interface ScorecardProps {
  summary: BacktestSummaryItem;  // overall summary
}
```

KPI 卡片颜色逻辑：
- 绿色(text-green)：达标（胜率>55%, 盈亏比>1.5, 评分>=B+）
- 黄色(text-yellow)：及格（胜率45-55%, 盈亏比1.0-1.5, 评分B/C）
- 红色(text-red)：预警（胜率<45%, 盈亏比<1.0, 评分D）

### 4.3 第2层组件：StrategyComparison

```tsx
// 表格: 按 setup_type 维度的 summary 逐行展示
// 数据来源: summaries.filter(s => s.groupType === "setup_type")
// 排序: 按 profit_factor 降序

interface StrategyComparisonProps {
  summaries: BacktestSummaryItem[];  // setup_type summaries only
}
```

每行末尾加评级 Badge（🟢优/🟡中/🔴差），评级规则写死在前端。

### 4.4 第3层组件：JudgmentValidation

三个子面板用 Tab 或折叠面板组织：

```tsx
interface JudgmentValidationProps {
  tradeStageSummaries: BacktestSummaryItem[];      // trade_stage 分组
  maturitySummaries: BacktestSummaryItem[];         // entry_maturity 分组
  setupTypeSummaries: BacktestSummaryItem[];        // setup_type 分组 (MAE)
  rankingEffectiveness: RankingEffectivenessData;   // 新API返回
}
```

### 4.5 第4层组件：EvaluationDetail

```tsx
// Tab切换: 入场信号 / 观察信号
// 通过 signalFamily query param 过滤API请求
// 点击行展开: 解析 factor_snapshot_json / trade_plan_json 渲染详情

interface EvaluationDetailProps {
  backtestRunId: string;
}
```

展开行渲染 factor_snapshot_json 的关键字段映射：

| JSON key | 展示名 | 展示方式 |
|----------|--------|---------|
| ma100_breakout_days | MA100突破 | ✅ 突破N日 / ❌ 未突破 |
| bottom_divergence_state | 底背离 | ✅ confirmed / ❌ rejected |
| trendline_breakout | 趋势线突破 | ✅ 突破(触碰N次) / ❌ 未突破 |
| gap_is_breakaway | 突破性缺口 | ✅ 有 / ❌ 无 |
| low_123_state | 低位结构 | ✅ confirmed / ⚠️ structure_only |

---

## 五、数据库迁移

### 5.1 SQL 变更

```sql
ALTER TABLE five_layer_backtest_group_summaries
  ADD COLUMN profit_factor FLOAT,
  ADD COLUMN avg_holding_days FLOAT,
  ADD COLUMN max_consecutive_losses INTEGER,
  ADD COLUMN plan_execution_rate FLOAT,
  ADD COLUMN stage_accuracy_rate FLOAT,
  ADD COLUMN system_grade VARCHAR(4);
```

### 5.2 兼容性

- 新字段全部 nullable，不影响已有数据
- 已完成的 backtest run 如需新指标，重跑 `compute_summaries()` 即可回填
- 前端对 null 值统一显示 `--`

---

## 六、实施计划

### Phase 1 (P0) — 核心指标 + 体检卡

**目标：** 打开页面30秒看到系统好不好

| 步骤 | 任务 | 涉及文件 |
|------|------|---------|
| 1.1 | DB migration: GroupSummary 加6个字段 | backtest_models.py, summary_repo.py |
| 1.2 | aggregate_group() 新增 profit_factor / avg_holding_days / max_consecutive_losses / plan_execution_rate / stage_accuracy_rate | group_summary_aggregator.py |
| 1.3 | 新建 SystemGrader + 集成到 compute_summaries | system_grader.py, backtest_service.py |
| 1.4 | API schema 新增字段 | five_layer_backtest.py (schemas) |
| 1.5 | 前端 SystemScorecard 组件 | SystemScorecard.tsx |
| 1.6 | 前端 StrategyComparison 组件 | StrategyComparison.tsx |
| 1.7 | BacktestPage 重构顶部布局 | BacktestPage.tsx |

**验收标准：**
- 运行回测后，页面顶部显示6个KPI卡片+综合评分
- KPI卡片下方显示策略对比表，按盈亏比排序，带颜色评级
- 已有功能不受影响

### Phase 2 (P1) — 判断验证面板

**目标：** 验证选股系统的标签/分级是否准确

| 步骤 | 任务 | 涉及文件 |
|------|------|---------|
| 2.1 | 新增 ranking-effectiveness API | five_layer_backtest.py (endpoints), schemas |
| 2.2 | Evaluation to_dict() 暴露 factor_snapshot_json / trade_plan_json | backtest_models.py |
| 2.3 | API schema EvaluationItem 新增字段 | five_layer_backtest.py (schemas) |
| 2.4 | 前端 JudgmentValidation 组件 (3个子面板) | JudgmentValidation.tsx |
| 2.5 | BacktestPage 集成第3层 | BacktestPage.tsx |

**验收标准：**
- 交易阶段判断准确率面板：按 trade_stage 分组展示样本数、准确率、平均收益
- 入场成熟度验证面板：HIGH/MEDIUM/LOW 三级对比 + 分级一致性标识
- MAE精度分析面板：按策略展示平均MAE、偏早率

### Phase 3 (P2) — 个股明细优化

**目标：** 深入到单只股票看因子快照和交易计划执行

| 步骤 | 任务 | 涉及文件 |
|------|------|---------|
| 3.1 | 前端 EvaluationDetail 组件（分Tab + 展开行） | EvaluationDetail.tsx |
| 3.2 | factor_snapshot_json 结构化渲染 | EvaluationDetail.tsx |
| 3.3 | trade_plan_json 执行结果渲染 | EvaluationDetail.tsx |
| 3.4 | BacktestPage 替换现有候选列表 | BacktestPage.tsx |
| 3.5 | 前端 types 补充 | backtest.ts |

**验收标准：**
- 入场信号/观察信号分Tab展示
- 点击行可展开查看因子快照（MA100/底背离/趋势线/缺口状态）
- 点击行可展开查看止盈止损计划执行结果

---

## 七、风险与注意事项

### 7.1 数据依赖

- factor_snapshot_json 和 trade_plan_json 的填充依赖 ScreeningCandidate 表中对应字段是否有值
- 如果历史选股结果没有存储这些 JSON，展开行会显示空
- **建议**：先检查近期 ScreeningCandidate 数据的填充率

### 7.2 性能

- GroupSummary 新增计算（连续亏损、准确率等）需要遍历排序，O(n log n)
- 对于大区间回测（>1000 样本），aggregate_group 耗时可能增加
- **缓解**：新增计算都在内存中完成，无额外DB查询，可接受

### 7.3 向后兼容

- 所有新字段 nullable，不影响已有回测数据
- 前端对 null 统一显示 `--`，不会报错
- 旧的 API 响应是新响应的子集，不破坏外部调用方

### 7.4 不改动范围

以下不在本方案范围内（维持现状）：
- 回测引擎核心逻辑（EntryEvaluator / ObservationEvaluator / ExecutionModelResolver）
- 选股策略本身（YAML 规则、indicator 检测器）
- ExitSignalEvaluator（仍为 framework only）
- 旧版 backtest_engine.py（已被五层系统替代）

---

## 八、附录

### A. 综合评分算法详情

```
总分 = 胜率得分(0-40) + 盈亏比得分(0-40) + 稳定性得分(0-20)

胜率得分:
  ≥60%  → 40分
  ≥55%  → 35分
  ≥50%  → 25分
  ≥45%  → 15分
  <45%  → 5分

盈亏比得分:
  ≥2.0  → 40分
  ≥1.5  → 35分
  ≥1.2  → 25分
  ≥1.0  → 15分
  <1.0  → 5分

稳定性得分 (time_bucket_stability, 越低越好):
  ≤0.08 → 20分
  ≤0.12 → 15分
  ≤0.15 → 10分
  >0.15 → 5分

等级映射:
  ≥90 → A+    ≥80 → A    ≥70 → B+
  ≥55 → B     ≥40 → C    <40 → D
```

### B. 策略评级规则

```
🟢 优: win_rate_pct > 55 AND profit_factor > 1.5
🟡 中: win_rate_pct > 45 OR  profit_factor > 1.0
🔴 差: win_rate_pct ≤ 45 AND profit_factor ≤ 1.0
```

### C. 文件变更总览

```
修改:
  src/backtest/models/backtest_models.py          # GroupSummary 新增6字段 + Evaluation to_dict
  src/backtest/aggregators/group_summary_aggregator.py  # aggregate_group 新增5个计算
  src/backtest/repositories/summary_repo.py        # upsert_summary 新增参数
  src/backtest/services/backtest_service.py        # 集成 SystemGrader
  api/v1/schemas/five_layer_backtest.py            # Schema 新增字段
  api/v1/endpoints/five_layer_backtest.py          # 新增 ranking-effectiveness 端点
  apps/dsa-web/src/types/backtest.ts               # TS 类型新增
  apps/dsa-web/src/api/backtest.ts                 # 新增 API 调用
  apps/dsa-web/src/pages/BacktestPage.tsx          # 整体重构

新建:
  src/backtest/aggregators/system_grader.py        # 综合评分
  apps/dsa-web/src/components/backtest/SystemScorecard.tsx
  apps/dsa-web/src/components/backtest/StrategyComparison.tsx
  apps/dsa-web/src/components/backtest/JudgmentValidation.tsx
  apps/dsa-web/src/components/backtest/EvaluationDetail.tsx
```
