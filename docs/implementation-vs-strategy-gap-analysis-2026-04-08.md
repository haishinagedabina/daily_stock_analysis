# `daily_stock_analysis` 交易体系实现差异表

**日期**：2026-04-08  
**范围**：`daily_stock_analysis` 当前选股实现 vs 《短线操盘实战改造方案》/ Notion 交易体系方案  
**目的**：确认当前实现与目标方案的一致性，标记已对齐项、偏差项与后续修正重点。

---

## 一、总览结论

当前项目的选股功能已经**明显按“五层交易体系”落地**，不是旧式“多策略并列运行 + AI 辅助解释”的原始状态。系统已经具备：

- L1 市场环境层
- L2 板块/题材层
- L3 强势股池层
- L4 买点识别层
- L5 交易管理层
- 五层字段持久化/API 输出
- 策略 YAML 元数据编队（`system_role` / `strategy_family` / `setup_type`）

但当前实现与方案相比，仍存在若干关键偏差，尤其集中在：

1. **题材层和强势股池层的门控还不够硬**
2. **leader_pool 仍存在“个股极强可破格入池”的路径**
3. **AI 二筛已结构化增强，但仍偏解释器，不是完全意义上的系统裁判**
4. **部分策略 YAML 的语义仍残留旧分析器风格**

一句话总结：

> **架构已对齐，规则仍偏松。**

---

## 二、总览差异表

| 模块 | 方案要求 | 当前实现 | 结论 | 偏差等级 |
|---|---|---|---|---|
| L1 市场环境层 | 成为前置总开关 | 已实现 `MarketEnvironmentEngine` + `MarketGuard` | 基本对齐 | 低 |
| L2 板块/题材层 | 先板块后个股，成为强门控 | 已有板块热度/题材聚合/题材地位，但门控不够硬 | 部分偏差 | 中 |
| L3 强势股池层 | 只把值得跟踪的票放入池，不直接给执行结论 | 已有 `CandidatePoolClassifier`，但存在“个股极强破格”路径 | 有偏差 | 中高 |
| L4 买点识别层 | 收敛到少数核心买点 + 成熟度分级 | 已实现 `SetupResolver` + `EntryMaturityAssessor` | 基本对齐 | 低 |
| L5 交易管理层 | 执行级必须给仓位/止损/止盈/失效条件 | 已实现 `TradePlanBuilder` | 对齐 | 低 |
| 交易阶段字段 | 统一 `watch/focus/probe/add_on/...` | 已实现 `TradeStageJudge` + schema 持久化 | 对齐 | 低 |
| YAML 策略归位 | 策略按 `system_role / strategy_family / setup_type` 编队 | 已大体完成 | 对齐 | 低 |
| 删除异体系策略 | 删除缠论/波浪/箱体/情绪周期/金叉 | 已删除 | 对齐 | 低 |
| AI 二筛 | 从解释器升级为结构化裁判 | 已结构化增强，但仍偏解释/纠偏 | 部分偏差 | 中 |
| 通知/接口输出 | 输出环境/题材/阶段/计划 | 已输出五层字段 | 基本对齐 | 低 |

---

## 三、逐项差异分析

### 1）L1 市场环境层

#### 方案要求
- 先看大盘环境
- 环境决定是否出手
- 输出：
  - `aggressive`
  - `balanced`
  - `defensive`
  - `stand_aside`

#### 当前实现
相关文件：
- `src/services/market_environment_engine.py`
- `src/core/market_guard.py`

已实现：
- MA100 安全门控
- MA20 slope
- 涨跌家数/涨停跌停赚钱效应
- 输出 `market_regime` + `risk_level`

#### 差异判断
- **基本无核心偏差**
- 已符合“环境前置”的主线要求

#### 结论
**对齐**

---

### 2）L2 板块/题材层

#### 方案要求
- 先板块后个股
- 板块应成为候选股前置筛选层
- 输出：
  - 热点题材列表
  - 板块强度排名
  - 题材阶段标签
  - 龙头/核心股评分
- 关键硬规则：
  > **板块外个股不进入强势股池**

#### 当前实现
相关文件：
- `src/services/sector_heat_engine.py`
- `src/services/theme_aggregation_service.py`
- `src/services/theme_position_resolver.py`
- `src/services/theme_normalization_service.py`
- `src/services/theme_matching_service.py`
- `src/services/hot_theme_factor_enricher.py`

已实现能力：
- 板块热度
- 题材聚合
- 题材地位解析
- 热点题材归一化
- 个股题材匹配
- 龙头评分

#### 主要偏差

##### 偏差 A：题材层仍不是绝对总开关
当前 `ThemePositionResolver` 会给股票打上：
- `main_theme`
- `secondary_theme`
- `follower_theme`
- `fading_theme`
- `non_theme`

但更多仍是**结果标签化**，尚未彻底实现：
> 非主线题材股票不得进入后续强势股池

##### 偏差 B：外部主题上下文融合偏弱
虽然系统已经接入 OpenClaw 外部题材上下文，但 `theme_position` 的最终判断核心仍偏向：
- 本地 sector heat
- 板块状态 + 阶段映射

尚未完全达到“外部主题 + 本地板块 + 生命周期”三者深度融合的强门控效果。

##### 偏差 C：题材生命周期能力仍偏 MVP
方案更强调交易语义：
- 启动期
- 加速期
- 分歧期
- 退潮期

当前实现更多使用：
- `launch`
- `ferment`
- `expand`
- `climax`
- `fade`

可以近似表达，但与方案中的交易语义化生命周期还不完全等价。

#### 结论
**部分对齐，但离“强门控型题材层”仍有距离**

#### 偏差等级
**中**

---

### 3）L3 强势股池层

#### 方案要求
- 强势股池用于回答“哪些值得跟踪”，而非直接给执行结论
- 输出：
  - `watchlist`
  - `focus_list`
  - `leader_pool`
- 关键硬规则：
  > 不在强势股池中的标的，不得进入 `add_on_strength`

#### 当前实现
相关文件：
- `src/services/candidate_pool_classifier.py`

当前规则包含：
- 主线路径：
  - `leader_score` 高 + `main/secondary_theme` → `leader_pool`
- 破格路径：
  - `extreme_strength_score >= 80` + `has_entry_core_hit` → `leader_pool`

#### 主要偏差

##### 偏差 A：存在“非主线题材票靠个股强度破格进入 leader_pool”的路径
按方案理解，`leader_pool` 应更强调：
- 强题材
- 龙头性
- 板块地位

当前实现允许：
- 个股极强 + 核心买点
- 即便不是明确主线题材，也可能进入 `leader_pool`

这会削弱：
> 先板块主线，后个股强势

##### 偏差 B：L3 仍混入部分执行倾向
虽然该层已被定义为 stock pool，但分类条件仍依赖：
- `entry_maturity`
- `has_entry_core_hit`

这会让股票池层带上一部分执行预判色彩，而不是纯粹的“池子分层”。

#### 结论
**结构已实现，但门槛口径仍偏宽**

#### 偏差等级
**中高**

---

### 4）L4 买点识别层

#### 方案要求
收敛到核心买点：
- `bottom_divergence_breakout`
- `low123_breakout`
- `trend_breakout`
- `trend_pullback`
- `gap_breakout`

输出成熟度：
- `low`
- `medium`
- `high`

#### 当前实现
相关文件：
- `src/services/setup_resolver.py`
- `src/services/entry_maturity_assessor.py`

当前做法：
- 多策略命中后，收敛成一个 `setup_type`
- 再根据检测器状态评估 `entry_maturity`

#### 差异判断
- 核心买点集合与方案一致
- 成熟度评估方式与方案主线一致
- 暂无明显方向性偏差

#### 小瑕疵
个别成熟度规则仍偏简化，例如：
- `trend_pullback` 主要依赖 `pullback_ma20`
- `trend_breakout` 主要依赖 breakout 天数

后续若要更贴近原方案，可增强结构完整性判定。

#### 结论
**基本对齐**

#### 偏差等级
**低**

---

### 5）L5 交易阶段裁决

#### 方案要求
统一状态：
- `stand_aside`
- `watch`
- `focus`
- `probe_entry`
- `add_on_strength`
- `reject`

并通过环境/题材/买点成熟度/止损条件来裁决。

#### 当前实现
相关文件：
- `src/services/trade_stage_judge.py`

已实现硬规则：
- `stand_aside` 环境 → 最高 `watch`
- `fading_theme` → `watch`
- 无买点 → `watch`
- 成熟度低 → `focus`
- 无止损锚点 → `focus`
- 高成熟度 + 龙头池 → `add_on_strength`
- 中高成熟度 → `probe_entry`

#### 主要偏差
本层核心逻辑问题不大，主要偏差来自上游 L3：
- 如果 `leader_pool` 口径偏宽
- `add_on_strength` 也会被间接放宽

#### 结论
**本层基本对齐，问题主要继承自 L3**

#### 偏差等级
**低到中**

---

### 6）交易管理层 / Trade Plan

#### 方案要求
执行级候选必须输出：
- 初始仓位
- 加仓条件
- 止损依据
- 止盈计划
- 失效条件
- 风险等级

#### 当前实现
相关文件：
- `src/services/trade_plan_builder.py`

当前做法：
- 仅对 `probe_entry` / `add_on_strength` 生成 `TradePlan`
- 输出：
  - `initial_position`
  - `add_rule`
  - `stop_loss_rule`
  - `take_profit_plan`
  - `invalidation_rule`
  - `risk_level`
  - `holding_expectation`

#### 差异判断
- 与方案要求一致
- 无明显偏差

#### 结论
**对齐**

#### 偏差等级
**低**

---

### 7）策略 YAML 编队归位

#### 方案要求
策略不再全部作为候选生成器，而要拥有明确角色：
- `entry_core`
- `stock_pool`
- `observation`
- 等

#### 当前实现
已见 YAML 示例：
- `bottom_divergence_double_breakout`
  - `system_role: entry_core`
  - `strategy_family: reversal`
  - `setup_type: bottom_divergence_breakout`
- `extreme_strength_combo`
  - `system_role: stock_pool`
  - `strategy_family: momentum`
- `bull_trend`
  - `system_role: stock_pool`
  - `strategy_family: trend`

#### 主要偏差

##### 偏差 A：部分 YAML 文案仍带旧系统味道
例如 `bull_trend.yaml` 的 instructions 仍偏向：
- 直接给买入/观望/减仓倾向

而非纯粹服务于“股票池层角色说明”。

##### 偏差 B：角色归位已完成，但语义收敛尚未完全完成
代码层已经按新体系在使用；
但策略描述层仍残留旧分析器风格。

#### 结论
**代码口径已对齐，策略叙事层仍有轻微残留**

#### 偏差等级
**低到中**

---

### 8）删除异体系策略

#### 方案要求
删除：
- `box_oscillation`
- `chan_theory`
- `wave_theory`
- `emotion_cycle`
- `ma_golden_cross`

#### 当前实现
当前 `strategies/` 目录中已不再包含上述文件。

#### 结论
**完全对齐**

#### 偏差等级
**低**

---

### 9）AI 二筛

#### 方案要求
AI 不再自由发挥，而要输出固定结构：
- `environment_ok`
- `theme_position`
- `trade_stage`
- `entry_maturity`
- `risk_level`
- `stop_loss`
- `take_profit_plan`
- `invalidation_rule`

#### 当前实现
相关文件：
- `src/services/candidate_analysis_service.py`
- `src/services/ai_review_protocol.py`

当前状态：
- AI 已接收五层上下文
- AI 输出被协议层解析为：
  - `ai_trade_stage`
  - `ai_reasoning`
  - `ai_confidence`
- 规则层 stage 和 AI stage 存在约束关系

#### 主要偏差

##### 偏差 A：AI 仍更像“结构化解释器”，不是强裁判
当前工作流仍是：
- 规则层先完成主裁决
- AI 再解释、归纳、轻纠偏

而不是让 AI 成为固定协议下的主审查层。

##### 偏差 B：AI 输出结构还不够完整公开
候选 schema 已暴露：
- `ai_trade_stage`
- `ai_reasoning`
- `ai_confidence`

但没有完整公开整套 AI 审核结构结果。

#### 结论
**已明显升级，但尚未达到“裁判型 AI”目标状态**

#### 偏差等级
**中**

---

### 10）API / 数据存储 / 输出层

#### 方案要求
前端、通知、API 都围绕统一五层字段输出。

#### 当前实现
相关文件：
- `api/v1/schemas/screening.py`
- `api/v1/endpoints/screening.py`
- `src/storage.py`
- `src/services/screening_notification_service.py`

当前状态：
- API schema 已包含：
  - `trade_stage`
  - `setup_type`
  - `entry_maturity`
  - `risk_level`
  - `market_regime`
  - `theme_position`
  - `candidate_pool_level`
  - `trade_plan`
- 数据库存储已持久化这些字段
- 通知层已引用这些字段进行输出

#### 差异判断
- 无本质偏差
- 表明该体系已经贯通到 API 和输出层，而非仅停留于内部对象

#### 结论
**对齐**

#### 偏差等级
**低**

---

## 四、最关键的 5 条实质差异

| 排名 | 差异 | 说明 |
|---:|---|---|
| 1 | L2/L3 门控还不够硬 | 题材层还没彻底成为“板块外不得入池”的总开关 |
| 2 | `leader_pool` 口径偏宽 | 允许“极强个股 + entry_core”破格进池 |
| 3 | `add_on_strength` 间接受 L3 放宽影响 | 因 `leader_pool` 可破格，所以 `add_on_strength` 也被间接放宽 |
| 4 | AI 二筛仍偏解释器 | 已结构化增强，但还不是强裁判 |
| 5 | 部分 YAML 说明仍带旧策略分析器味道 | 尤其 `bull_trend` 这类 `stock_pool` 策略 |

---

## 五、文件级差异定位

### 高优先级关注文件

#### 1. `src/services/candidate_pool_classifier.py`
**问题：**
- 强势股池口径偏宽
- 非题材主线个股有破格路径

**建议关注：**
- `leader_pool` 的两条进入路径
- 是否要强制依赖 `theme_position`

---

#### 2. `src/services/theme_position_resolver.py`
**问题：**
- 题材地位解析偏 MVP
- 外部主题上下文融合不够强

**建议关注：**
- 是否要把 OpenClaw 主题上下文真正引入 `theme_position` 裁决
- 是否要强化生命周期语义

---

#### 3. `src/services/trade_stage_judge.py`
**问题：**
- 本体问题不大
- 主要受上游 L3 影响

**建议关注：**
- 是否对 `add_on_strength` 再加一道 theme 约束

---

#### 4. `src/services/candidate_analysis_service.py` / `src/services/ai_review_protocol.py`
**问题：**
- AI 仍偏解释/纠偏，而非主裁判

**建议关注：**
- 是否增强 AI 固定输出结构
- 是否让 AI 审核字段更显式

---

#### 5. `strategies/bull_trend.yaml`
**问题：**
- 元数据已对齐
- 但 `instructions` 仍偏旧策略分析器风格，不像纯 stock pool 角色

---

## 六、最终判断

### 结论标签

> **架构已对齐，规则仍偏松。**

更具体地说：

- 当前系统已经走在目标方案定义的方向上
- 五层骨架已经建立
- 字段、持久化、API、通知也已贯通
- 真正的核心差异，不在于“有没有五层”
- 而在于“板块/题材这道门卡得还不够死”

---

## 七、后续建议（供下一步修复时使用）

建议优先级如下：

1. **先收紧 L2/L3 门控**
   - 强化 `theme_position` 对 `leader_pool` 的准入约束
   - 限制非主线题材票进入执行级阶段

2. **再收紧 `add_on_strength` 条件**
   - 除 `leader_pool` 外，增加题材地位硬校验

3. **增强题材生命周期与外部上下文融合**
   - 提升 L2 的“主线判断”能力

4. **把 AI 二筛进一步裁判化**
   - 使其更接近固定协议审查器，而非解释器

5. **清理 YAML 中残留的旧分析器语义**
   - 尤其是 `stock_pool` 类策略的 instructions

---

*写于 2026-04-08：用于记录当前 `daily_stock_analysis` 项目实现与目标交易体系方案之间的差异，为后续修正提供依据。*
