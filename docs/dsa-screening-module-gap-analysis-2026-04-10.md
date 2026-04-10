# DSA 选股系统模块对照表（对照 Notion 改造总纲）

> 生成时间：2026-04-10
> 范围：`E:\daily_stock_analysis` 当前选股实现，对照《短线操盘实战改造文档总览》及其子页面
> 目的：用于项目排期、代码收口、前后端字段统一与验收设计

---

## 0. 总体结论

| 维度 | 结论 |
|---|---|
| 总体方向 | **方向正确，主干已搭好** |
| 当前状态 | **半重构态 / 双轨并存态** |
| 最明显进展 | 已有五层语义、市场门控、题材前置、trade_stage、AI 二筛收束 |
| 最明显问题 | 新旧路径并存、统一对象未彻底成为唯一真相源、Trade Plan 和前后端字段闭环未完全完成 |
| 建议策略 | **继续收口，而不是继续横向加新策略** |

一句话判断：

**这项目已经从“策略拼盘”进化成“规则主导型多层选股系统”，但离 Notion 里那种彻底统一的母规范，还差最后一段收口工程。**

---

## 1. 总控编排层（Screening Orchestration）

### Notion 目标
- 固定执行顺序：市场环境 → 题材 → 强势股池 → 买点成熟度 → Trade Plan → AI 二筛 → 展示/通知
- 前序层有否决权，后序层不能推翻前序
- 任务可恢复、可追踪、可补跑

### 当前实现
核心入口：
- `src/services/screening_task_service.py`

当前 `execute_run()` 主流程已经完整覆盖：
- resolving_universe
- ingesting
- factorizing
- screening
- ai_enriching
- completed / completed_with_ai_degraded / failed

并具备：
- 失败重试
- 幽灵任务回收
- resume_from 补跑
- run_id 幂等
- stage 状态持久化

关键事实：
- 新主路径：`five_layer_pipeline`
- 旧补丁路径：`_apply_five_layer_decision(...)`

### 差距 / 问题
1. **双路径并存**
   - `five_layer_pipeline` 是新正统
   - `_apply_five_layer_decision` 是旧后置修补
   - 同样输入在不同路径下可能出现语义差异

2. **统一决策对象未上升为总控唯一输出**
   - 当前更像 `ScreeningCandidateRecord + ai_results + trade_plan_json + decision_context` 的组合

3. **编排完整，但决策主对象未彻底统一**
   - API / 前端 / 通知层仍可能各自消费不同字段组合

### 当前状态判断
**部分完成**

### 优先级
**P0**

### 建议代码落点
- `src/services/screening_task_service.py`
- `src/services/five_layer_pipeline.py`
- `src/schemas/trading_types.py`
- 建议新增：`src/services/candidate_decision_builder.py`

---

## 2. L1 市场环境层（Market Environment）

### Notion 目标
- 市场环境是总开关
- 输出：`aggressive / balanced / defensive / stand_aside`
- 影响候选上限、交易阶段上限、风险等级

### 当前实现
核心文件：
- `src/core/market_guard.py`
- `src/services/market_environment_engine.py`

已实现能力：
1. `MarketGuard`
   - 指数相对 MA100 的硬判断
   - 输出 `is_safe / index_price / index_ma100 / message`

2. `MarketEnvironmentEngine`
   - 综合：
     - MA100 上下
     - MA20 斜率
     - 涨停/跌停赚钱效应
     - 涨跌比
   - 输出：
     - `MarketEnvironment.regime`
     - `risk_level`

3. 编排层已真正消费结果
   - `stand_aside` → 0 候选
   - `defensive` → 候选上限减半
   - `TradeStageJudge` 再次约束后续阶段上限

### 差距 / 问题
1. L1 已经是当前收口较好的层，不是主要短板
2. 规则仍偏简化，尚未充分纳入：
   - 情绪退潮连续性
   - 主线赚钱效应 vs 全市场赚钱效应拆分
   - 盘中态 / 收盘态区分
3. 需检查所有旁路接口是否都严格遵守 L1 环境否决权

### 当前状态判断
**基本完成**

### 优先级
**P1**

### 建议代码落点
- `src/core/market_guard.py`
- `src/services/market_environment_engine.py`
- `src/services/screening_task_service.py`

---

## 3. L2 题材层（Theme Layer）

### Notion 目标
- 先识别市场主线/次主线，再匹配股票
- 输出：`main_theme / secondary_theme / follower_theme / fading_theme / non_theme`
- 题材层前置，不只是加分项
- 决定 universe 缩小、个股题材地位、后续阶段上限

### 当前实现
核心文件：
- `src/services/five_layer_pipeline.py`
- `src/services/theme_aggregation_service.py`
- `src/services/theme_position_resolver.py`
- `src/services/board_candidate_recall_service.py`
- `src/services/hot_theme_screener.py`

已实现能力：
1. `ThemeAggregationService`
   - 支持多个板块聚合到统一题材
   - 输出 `theme_score / status_rollup / stage_rollup`

2. `ThemePositionResolver.identify_main_themes()`
   - 已实现“先全市场识别主线，再匹配个股”

3. `resolve(stock_boards)` 输出 `ThemeDecision`
   - `theme_tag`
   - `theme_score`
   - `theme_position`
   - `sector_strength`
   - `leader_stocks`
   - `front_stocks`

4. `five_layer_pipeline` 已利用题材层缩小 universe

当前规则概览：
- hot + ferment/expand → `main_theme`
- hot + launch → `secondary_theme`
- warm + climax/fade → `fading_theme`
- warm + ferment/launch → `follower_theme`
- 其他 → `non_theme`

### 差距 / 问题
1. 题材层已成型，但还不够制度化
2. 题材生命周期语义仍偏轻，trade theme stage 尚未彻底闭环
3. 外部热点上下文融合仍偏轻量，未形成完整评分框架
4. 题材语义对后续层主路径已生效，但对展示/通知/AI 消费的一致性仍需强化

### 当前状态判断
**部分完成，接近成型**

### 优先级
**P0**

### 建议代码落点
- `src/services/theme_position_resolver.py`
- `src/services/theme_aggregation_service.py`
- `src/services/five_layer_pipeline.py`
- `src/services/hot_theme_factor_enricher.py`
- `src/services/theme_mapping_registry.py`

---

## 4. L3 强势股池层（Stock Pool Layer）

### Notion 目标
- 强势股池独立成层，而非简单分数排序
- 输出：`leader_pool / focus_list / watchlist`
- 主线题材内股票才可能进入高等级池
- 弱题材、退潮题材、非主线题材必须降级

### 当前实现
核心文件：
- `src/services/candidate_pool_classifier.py`
- `src/services/five_layer_pipeline.py`
- `src/services/factor_service.py`
- `src/services/extreme_strength_scorer.py`
- `src/services/leader_score_calculator.py`

已实现能力：
1. `FactorService` 已计算：
   - `leader_score`
   - `extreme_strength_score`

2. `CandidatePoolClassifier` 已输出：
   - `leader_pool`
   - `focus_list`
   - `watchlist`

3. 已有环境和题材硬门控：
   - `stand_aside` → `watchlist`
   - `non_theme / fading_theme` → `watchlist`
   - defensive 环境提高 `leader_pool` 门槛

### 差距 / 问题
1. 当前更像“分数 + 门槛分级”，业务语义还不够厚
2. 尚未完全成为候选组织中心，更多像后续 L5 的输入项
3. 与题材内龙头/前排/跟风相对位置的绑定还可以更系统化

### 当前状态判断
**部分完成**

### 优先级
**P1**

### 建议代码落点
- `src/services/candidate_pool_classifier.py`
- `src/services/five_layer_pipeline.py`
- `src/services/leader_score_calculator.py`
- `src/services/extreme_strength_scorer.py`

---

## 5. L4 买点层（Setup Layer）

### Notion 目标
统一买点语言：
- `bottom_divergence_breakout`
- `low123_breakout`
- `trend_breakout`
- `trend_pullback`
- `gap_breakout`

要求：
- 多策略命中后收敛成一个主 `setup_type`
- 输出至少包括：`setup_type / entry_maturity / setup_freshness`

### 当前实现
核心文件：
- `src/services/setup_resolver.py`
- `src/services/entry_maturity_assessor.py`
- `src/services/core_signal_identifier.py`
- `src/services/strategy_screening_engine.py`
- `src/services/factor_service.py`

已实现能力：
1. `SetupResolver`
   - 根据市场环境、题材位置、策略 family、策略得分收敛主 `setup_type`

2. `EntryMaturityAssessor`
   - 输出 `low / medium / high`
   - 基于 detector 状态进行规则映射

3. `setup_type` 已进入候选字段体系

4. YAML 策略已支持：
   - `system_role`
   - `strategy_family`
   - `setup_type`

### 差距 / 问题
1. `setup_freshness` 体现不明显
2. 并非所有策略都完全归位到统一 setup 体系
3. 展示层可能仍受 `matched_strategies` 叙事影响较大

### 当前状态判断
**部分完成，优先收口**

### 优先级
**P0**

### 建议代码落点
- `src/services/setup_resolver.py`
- `src/services/entry_maturity_assessor.py`
- `src/services/strategy_screening_engine.py`
- `strategies/*.yaml`

---

## 6. L5 交易阶段层（Trade Stage Layer）

### Notion 目标
统一执行权限语言：
- `stand_aside`
- `watch`
- `focus`
- `probe_entry`
- `add_on_strength`
- `reject`

要求：
- 环境差不能做
- 非主线降级
- 成熟度低降级
- 无止损不能进入执行级
- `TradeStage` 成为全系统核心输出语义

### 当前实现
核心文件：
- `src/services/trade_stage_judge.py`
- `src/services/five_layer_pipeline.py`
- `src/schemas/trading_types.py`

已实现能力：
1. `TradeStage` 枚举已定义
2. `TradeStageJudge` 已有硬规则：
   - `stand_aside` 环境 → 最高 `watch`
   - `fading/non_theme + 无买点 + low` → `reject`
   - `setup_type == none` → `watch`
   - `entry_maturity == low` → `focus`
   - 无止损锚点 → `focus`
   - defensive / 非主线 → `probe_entry` 封顶
3. pipeline 已回写核心字段到 candidate

### 差距 / 问题
1. `trade_stage` 已关键，但还不是全链路唯一语言
2. `reject / stand_aside / watch` 的展示和通知口径可能尚未统一
3. 阶段迁移的历史一致性解释链还不够完整

### 当前状态判断
**部分完成，优先收口**

### 优先级
**P0**

### 建议代码落点
- `src/services/trade_stage_judge.py`
- `src/services/five_layer_pipeline.py`
- `src/services/screening_task_service.py`
- 前端详情 / 列表 API 消费层

---

## 7. Trade Plan 层（执行计划层）

### Notion 目标
Trade Plan 是执行层最小控制单元，仅在：
- `probe_entry`
- `add_on_strength`

时生成。

至少包含：
- `initial_position`
- `add_rule`
- `stop_loss_rule`
- `take_profit_plan`
- `invalidation_rule`
- `holding_expectation`
- `execution_note`

并要求：
- 没有止损锚点，不得进入执行级

### 当前实现
核心文件：
- `src/services/trade_plan_builder.py`
- `src/services/five_layer_pipeline.py`

已实现能力：
1. `TradePlanBuilder.build(...)`
   - 仅 `probe_entry / add_on_strength` 生成 plan
   - 其他阶段返回 `None`

2. 已有字段：
   - `initial_position`
   - `add_rule`
   - `stop_loss_rule`
   - `take_profit_plan`
   - `invalidation_rule`
   - `risk_level`
   - `holding_expectation`

3. pipeline 已写入 `candidate.trade_plan_json`

4. L5 前已通过 `has_stop_loss` 控制执行级上限

### 差距 / 问题
1. **缺 `execution_note`**
2. 目前更多是模板驱动，尚未充分利用个股具体锚点和结构位
3. `TradePlan` 更像附属 JSON，还不是前后端统一消费的一等公民
4. Plan 与 AI 二筛之间的统一消费关系仍可加强

### 当前状态判断
**部分完成，关键缺口**

### 优先级
**P0**

### 建议代码落点
- `src/services/trade_plan_builder.py`
- `src/services/five_layer_pipeline.py`
- `src/schemas/trading_types.py`
- `src/services/ai_review_protocol.py`
- API schema / frontend detail view

---

## 8. AI 二筛层（AI Review Layer）

### Notion 目标
- AI 不是主脑，而是结构化复核器
- 必须输出固定 schema
- 与规则冲突时，规则优先
- 证据不足优先降级
- JSON 失败 / 超时 /异常时可回退，不阻断主链路

### 当前实现
核心文件：
- `src/services/candidate_analysis_service.py`
- `src/services/ai_review_protocol.py`
- `src/services/screening_task_service.py`

已实现能力：
1. AI 只分析 top_k
2. `AiReviewProtocol` 已优先解析 JSON，再 fallback 关键词
3. 已解析字段包括：
   - `suggested_stage`
   - `confidence`
   - `reasoning`
   - `risk_flags`
   - `environment_ok`
   - `theme_alignment`
   - `entry_quality`
4. 已应用 regime ceiling，规则冲突时规则优先
5. AI 失败不阻断任务，支持 degraded 完成态

### 差距 / 问题
1. schema 比以前强很多，但离 Notion 终版固定字段集还有距离
2. AI 输出与最终 candidate 决策对象尚未完全合流
3. AI 解释与规则解释可能仍是两套叙事
4. 冲突展示与审计信息仍可加强

### 当前状态判断
**部分完成**

### 优先级
**P1**

### 建议代码落点
- `src/services/ai_review_protocol.py`
- `src/services/candidate_analysis_service.py`
- `src/services/screening_task_service.py`
- candidate detail API / 前端详情页

---

## 9. 策略体系与 YAML 元数据层

### Notion 目标
- 清理偏离母系统的策略
- 每个策略都应有明确系统角色：
  - `entry_core`
  - `stock_pool`
  - `theme_score`
  - `confirm`
  - `bonus_signal`
  - `observation`
- 策略不再直接争夺最终推荐权

### 当前实现
核心文件：
- `strategies/*.yaml`
- `src/services/strategy_screening_engine.py`
- `src/services/strategy_dispatcher.py`
- `src/services/setup_resolver.py`

已实现能力：
1. YAML 已支持：
   - `system_role`
   - `strategy_family`
   - `applicable_market`
   - `applicable_theme`
   - `setup_type`

2. `StrategyScreeningEngine` 已可输出最佳 entry_core setup 元数据

3. `StrategyDispatcher` 已按环境过滤允许策略

### 差距 / 问题
1. 元数据已具备，但“完全归位”还未彻底完成
2. 需对所有策略做一次全量 audit，检查字段完备性与角色边界
3. 像 `extreme_strength_combo` 这样的特殊路径要警惕例外膨胀

### 当前状态判断
**部分完成，必须 audit**

### 优先级
**P0**

### 建议代码落点
- `strategies/*.yaml`
- `src/services/strategy_screening_engine.py`
- `src/services/strategy_dispatcher.py`
- `src/services/setup_resolver.py`

---

## 10. 因子与信号层（Factor / Detector Layer）

### Notion 目标
- 下层 detector 只提供证据，不直接给最终建议
- 上层统一消费这些证据，形成 setup / maturity / plan

### 当前实现
核心文件：
- `src/services/factor_service.py`
- `src/indicators/*`
- `src/services/core_signal_identifier.py`

已实现能力：
1. 因子层已经较扎实
   - MA、量比、突破、流动性、上市天数、风险标记等
2. detector 丰富
   - 底背离、gap、limit up、123、趋势线、MA breakout 等
3. 因子层已经主要作为证据提供者，被上层消费

### 差距 / 问题
1. 这一层不是当前主要短板
2. 需要留意 detector 输出字段与状态命名是否完全标准化
3. 少数策略可能仍存在直接消费 detector、绕过统一 setup 层的风险

### 当前状态判断
**基本可用**

### 优先级
**P2**

### 建议代码落点
- `src/services/factor_service.py`
- `src/indicators/*`
- `src/services/core_signal_identifier.py`

---

## 11. 统一数据结构 / Schema 层

### Notion 目标
- 全系统围绕统一 `CandidateDecision / TradePlan / ThemeDecision` 等对象运转
- 前后端、通知、历史详情、AI prompt 都消费同一语义对象
- 避免散字段拼装

### 当前实现
核心文件：
- `src/schemas/trading_types.py`
- `src/services/screener_service.py`
- `src/services/screening_task_service.py`

已实现能力：
1. `trading_types.py` 已定义：
   - `MarketEnvironment`
   - `ThemeDecision`
   - `SetupDecision`
   - `TradePlan`
   - `CandidateDecision`
   - 以及一组核心枚举

### 差距 / 问题
这是全系统当前**最关键但也最没彻底打通的地方**。

1. `CandidateDecision` 更像理想设计，而不是当前唯一事实对象
2. 当前运行链路更常见的是：
   - `ScreeningCandidateRecord`
   - `trade_plan_json`
   - `ai_results`
   - `decision_context`
   - DB row payload
3. 容易出现字段漂移、语义重复、前端/通知/API 各自拼字段的问题

### 当前状态判断
**未完成（核心收口项）**

### 优先级
**P0 / 核心收口项**

### 建议代码落点
- `src/schemas/trading_types.py`
- `src/services/screening_task_service.py`
- `src/services/five_layer_pipeline.py`
- 建议新增：
  - `src/services/candidate_decision_builder.py`
  - `src/schemas/candidate_payload_schema.py`

---

## 12. API / 前端展示层（Presentation Layer）

### Notion 目标
- 前端和通知层不重新决策，只展示统一结果
- 列表页、详情页、通知内容都围绕：
  - `trade_stage`
  - `setup_type`
  - `entry_maturity`
  - `theme_position`
  - `trade_plan`
  - `ai_review`
- 主叙事应是“当前处于什么交易阶段，能不能做，为什么”

### 当前实现
从 README 和目录结构看：
- Web / Desktop / Bot / API 多端已存在
- 智能选股页已有：
  - 运行状态面板
  - 候选详情
  - 命中策略中文名
  - `phase_results`
  - `phase_explanations`

### 差距 / 问题
1. 展示主叙事可能仍偏“命中策略”
2. Trade Plan 是否已成为前端主展示块，还不明确
3. `phase_results / phase_explanations` 与统一 schema 的关系需要进一步标准化
4. 前端和通知层仍可能有二次解释逻辑

### 当前状态判断
**部分完成**

### 优先级
**P1**

### 建议代码落点
- `apps/dsa-web/*`
- `api/v1/*`
- `src/services/screening_task_service.py`
- `src/formatters.py`
- `src/notification.py`

---

## 13. 通知 / Bot / 报告层

### Notion 目标
- 通知层只消费结果，不二次裁决
- 输出口径统一
- 不再依赖“命中策略 + AI 文案”拼接通知

### 当前实现
相关目录：
- `src/notification_sender/*`
- `bot/*`
- `templates/*`
- `src/formatters.py`
- `src/notification.py`

已实现能力：
- 多渠道通知体系成熟
- 模板能力完整
- Bot / Web / API 已接通

### 差距 / 问题
1. 通知层大概率仍处于“兼容旧字段 + 新字段混用”阶段
2. 如果最终语义以 `trade_stage + trade_plan` 为主，通知模板需重构
3. 这是语义漂移风险较高的一层，但不建议早改，避免返工

### 当前状态判断
**部分完成**

### 优先级
**P2**

### 建议代码落点
- `src/notification.py`
- `src/formatters.py`
- `templates/*`
- `src/notification_sender/*`

---

## 14. 测试与验收层

### Notion 目标
- 固定输入 → 固定输出
- 建立五层决策链 golden cases
- 验证：
  - 市场环境门控
  - 题材层前置
  - setup 收敛
  - trade_stage 裁决
  - Trade Plan 生成
  - AI 冲突处理

### 当前实现
已有测试较多，例如：
- `tests/test_ai_review_protocol.py`
- `tests/test_agent_pipeline.py`
- `tests/test_analysis_api_contract.py`
- `tests/test_board_candidate_recall_service.py`

### 差距 / 问题
1. 测试很多，但未必围绕“五层统一决策对象”组织
2. 缺少一眼能判断系统是否收口完成的 golden cases
3. 建议补：
   - 同一 snapshot + market env + board map → 期望 `candidate_decision`

### 当前状态判断
**部分完成**

### 优先级
**P1**

### 建议代码落点
- `tests/test_five_layer_pipeline.py`
- `tests/test_trade_stage_judge.py`
- `tests/test_trade_plan_builder.py`
- `tests/test_setup_resolver.py`
- 建议新增：`tests/golden_cases/*`

---

## 15. 现状总评表

| 模块 | 当前状态 | 结论 |
|---|---|---|
| 总控编排 | 任务流完整，但双轨并存 | **部分完成** |
| L1 市场环境 | 已实质控制候选输出 | **基本完成** |
| L2 题材层 | 已前置、已缩 universe | **部分完成，接近成型** |
| L3 强势股池 | 已分级，但语义还可加厚 | **部分完成** |
| L4 买点层 | 已有 setup 收敛 + maturity | **部分完成，优先收口** |
| L5 交易阶段 | 已关键、规则已落地 | **部分完成，优先收口** |
| Trade Plan | 已接线，但仍偏模板附属 | **部分完成，关键缺口** |
| AI 二筛 | 已结构化，规则优先 | **部分完成** |
| 策略元数据体系 | 已开始归位 | **部分完成，必须 audit** |
| 统一 Schema | 理想模型已写出，未成为唯一真相源 | **未完成（关键）** |
| API / 前端展示 | 已展示五层信息，但叙事仍混合 | **部分完成** |
| 通知层 | 功能成熟，语义未必统一 | **部分完成** |
| 测试 / 验收 | 有测试，缺五层 golden case 骨架 | **部分完成** |

---

## 16. 优先级建议

### P0：必须先做的 5 件事
1. **统一最终决策对象**
   - 让 `CandidateDecision` 真正成为唯一真相源

2. **彻底单轨化五层主路径**
   - 淘汰或收编 `_apply_five_layer_decision` 后置老路

3. **补完 Trade Plan 成为一等公民**
   - 补 `execution_note`
   - API / 前端 / AI 统一消费

4. **把 setup / trade_stage 变成前端主叙事**
   - 降低“命中策略名”在展示中的中心地位

5. **全量审计策略 YAML 元数据**
   - 确保每个策略都清楚归属某层角色

### P1：随后做的 4 件事
1. 强化题材层生命周期与龙头层级语义
2. 补 AI 冲突展示与审计链
3. 做五层 golden cases
4. 收一遍 API schema 与前端字段契约

### P2：最后收边
1. 通知模板统一
2. detector 字段标准化细修
3. 特例策略去例外化

---

## 17. 建议拆成的改造任务单

### 任务 1：统一 CandidateDecision 输出总线
- **目标**：所有候选最终都落成统一对象
- **涉及**：`trading_types.py`、`screening_task_service.py`、`five_layer_pipeline.py`、DB payload schema
- **验收**：candidate detail/list/API 不再依赖散字段拼装

### 任务 2：五层主路径单轨化
- **目标**：所有筛选都走同一条五层裁决链
- **涉及**：`screening_task_service.py`、`_apply_five_layer_decision` 收编/下线
- **验收**：不存在“新路径/旧路径行为分叉”

### 任务 3：Trade Plan 一等公民化
- **目标**：Trade Plan 不再是附属 JSON
- **涉及**：`trade_plan_builder.py`、schema / API / frontend
- **验收**：
  - `probe_entry / add_on_strength` 必有 plan
  - `focus/watch/reject` 明确无 plan

### 任务 4：策略体系全量归位
- **目标**：每个策略都清楚服务于某层，而非争抢最终结论
- **涉及**：`strategies/*.yaml`、`strategy_screening_engine.py`、`setup_resolver.py`
- **验收**：每个策略具备完整元数据并通过 audit

### 任务 5：展示层语义统一
- **目标**：前端、通知、详情页都以 `trade_stage + setup + plan` 为主
- **涉及**：`api/*`、`apps/dsa-web/*`、`formatters.py`、`notification.py`
- **验收**：用户看到的是“当前阶段、为什么、怎么做”，而不是一堆命中的策略名

---

## 18. 结尾判断

当前系统已经不是传统“条件筛子”，而是：

**“行情同步 → 因子快照 → 策略首筛 → 五层裁决 → AI 二筛补充 → 多端展示”的结构化选股系统。**

它的真正问题已经不是“能不能选”，而是：

**如何把已经长出来的正确骨架，彻底收口成一套统一、稳定、可解释、可验收的交易系统母规范。**
