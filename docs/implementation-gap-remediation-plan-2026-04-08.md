# `daily_stock_analysis` 交易体系修正清单

**日期**：2026-04-08  
**对应差异文档**：`docs/implementation-vs-strategy-gap-analysis-2026-04-08.md`  
**目标**：将当前实现从“架构已对齐，规则仍偏松”推进到更严格贴合《短线操盘实战改造方案》的状态。  

---

## 一、修正目标总览

本轮修正不建议“大拆大改”，而建议遵循以下原则：

1. **先收紧门控，再增强表达**
2. **先改规则口径，再改 AI 协议**
3. **先保证 L2/L3/L5 一致，再清理 YAML 叙事**
4. **优先做低风险、高收益的规则收敛**

本次修正优先级建议：

### P0（最高优先级）
- 收紧 L2/L3 门控
- 收紧 `leader_pool` 准入逻辑
- 收紧 `add_on_strength` 准入逻辑

### P1（高优先级）
- 强化题材生命周期与外部上下文融合
- 明确 AI 二筛协议化输出

### P2（中优先级）
- 清理 YAML 中残留的旧分析器语义
- 完善前端/通知对更严格规则的展示解释

---

## 二、修正项总表

| 优先级 | 修正项 | 目标 | 主要文件 |
|---|---|---|---|
| P0 | 收紧强势股池准入 | 让 `leader_pool` 更严格依赖题材主线 | `src/services/candidate_pool_classifier.py` |
| P0 | 收紧 `add_on_strength` 条件 | 防止非主线/破格票进入执行强化阶段 | `src/services/trade_stage_judge.py` |
| P0 | 强化 L2→L3 约束链 | 让题材层真正成为前置门控 | `src/services/theme_position_resolver.py` / `src/services/screening_task_service.py` |
| P1 | 补强题材生命周期语义 | 让题材判断更贴合交易阶段语言 | `src/services/sector_heat_engine.py` / `src/services/theme_aggregation_service.py` |
| P1 | 强化外部热点上下文融合 | 提升 OpenClaw 题材输入对最终判定的影响力 | `src/services/theme_position_resolver.py` |
| P1 | AI 二筛协议化 | 让 AI 更像裁判而非解释器 | `src/services/candidate_analysis_service.py` / `src/services/ai_review_protocol.py` |
| P2 | 清理 YAML 旧语义 | 让 `stock_pool`/`entry_core` 文案更符合新体系 | `strategies/*.yaml` |
| P2 | 增补测试 | 防止规则收紧后回退 | `tests/test_e2e_five_layer_local.py` 等 |

---

## 三、详细修正清单

---

### 修正项 1：收紧 `leader_pool` 准入逻辑

**优先级：P0**

### 当前问题
`CandidatePoolClassifier` 存在如下路径：
- `leader_score` + 题材位置 → `leader_pool`
- `extreme_strength_score >= 80` + `has_entry_core_hit` → `leader_pool`

第二条路径会导致：
- 非主线题材股票
- 仅靠个股极强 + 核心买点
- 也能进入 `leader_pool`

这会削弱：
> 先题材、后个股、再买点

### 目标
将 `leader_pool` 收紧为：
- **主线题材优先**
- **龙头性优先**
- **极端强势仅作为增强条件，不作为单独破格通道**

### 主要文件
- `src/services/candidate_pool_classifier.py`

### 建议改法
#### 方案 A（推荐）
把 `leader_pool` 条件改为必须满足：
- `theme_position in {main_theme, secondary_theme}`
- 且满足以下其一：
  - `leader_score >= threshold`
  - `extreme_strength_score >= threshold AND leader_score >= secondary_threshold`

也就是说：
- **极端强势不能脱离题材位置独立晋级**
- 最多只能在主线题材内部加速晋级

#### 方案 B（保守过渡）
保留破格路径，但新增中间状态，例如：
- `exceptional_watch`
- 或仍归入 `focus_list`

避免直接进入 `leader_pool`

### 验收标准
- `non_theme` 票不得直接进入 `leader_pool`
- `follower_theme` 票默认不得进入 `leader_pool`
- `leader_pool` 结果应显著更贴近题材主线

---

### 修正项 2：收紧 `add_on_strength` 准入逻辑

**优先级：P0**

### 当前问题
`TradeStageJudge` 当前对 `add_on_strength` 的依赖是：
- 高成熟度
- `pool_level == LEADER_POOL`

这本身没错，但由于 `leader_pool` 口径偏宽，导致：
- 上游一旦放宽
- `add_on_strength` 也会被间接放宽

### 目标
让 `add_on_strength` 成为更严格的执行强化阶段，只保留给：
- 主线题材
- 龙头池
- 高成熟度
- 有止损锚点
- 环境不差

### 主要文件
- `src/services/trade_stage_judge.py`

### 建议改法
新增硬约束：
- 仅 `theme_position == main_theme` 时允许 `add_on_strength`
- `secondary_theme` 最高只到 `probe_entry`（可选）
- `follower_theme / non_theme / fading_theme` 不得进入 `add_on_strength`

可考虑的严格版逻辑：
- `main_theme + leader_pool + HIGH + has_stop_loss + balanced/aggressive` → `add_on_strength`
- `secondary_theme + leader_pool + HIGH` → 最多 `probe_entry`
- 其他 → 不进入 `add_on_strength`

### 验收标准
- `add_on_strength` 候选数量明显收敛
- `add_on_strength` 候选应几乎全部来自主线强题材
- 通知/前端展示的执行级标的质量提升

---

### 修正项 3：强化 L2→L3 约束链，让题材层成为前置门控

**优先级：P0**

### 当前问题
虽然系统已有 `theme_position`，但从实现上看，它更像：
- 分类标签
而不是：
- 决定哪些票可以继续推进的前置门

### 目标
明确建立以下链路：

> L2 题材地位 → 决定能否进入 L3 某些池子 → 决定能否进入 L5 执行级

### 主要文件
- `src/services/theme_position_resolver.py`
- `src/services/candidate_pool_classifier.py`
- `src/services/screening_task_service.py`

### 建议改法
在五层决策链中明确加入约束说明：
- `main_theme`：可进入 `leader_pool` / `focus_list`
- `secondary_theme`：可进入 `focus_list`，审慎进入 `leader_pool`
- `follower_theme`：默认最高 `focus_list`
- `non_theme`：默认最高 `watchlist`
- `fading_theme`：最高 `watch`

必要时可在 `_apply_five_layer_decision()` 中加入显式 guard，而非完全依赖下游分类器自己约束。

### 验收标准
- 题材位置对池子分级结果有稳定、一致的约束作用
- 不再出现明显“题材弱但直接执行级”的反直觉结果

---

### 修正项 4：补强题材生命周期语义

**优先级：P1**

### 当前问题
当前系统已有：
- `launch`
- `ferment`
- `expand`
- `climax`
- `fade`

但与方案中的交易语义：
- 启动期
- 加速期
- 分歧期
- 退潮期

仍有差距。

### 目标
让题材阶段更贴近交易决策语言，而不是仅停留在热度标签层。

### 主要文件
- `src/services/sector_heat_engine.py`
- `src/services/theme_aggregation_service.py`

### 建议改法
#### 最小改动版
保留现有枚举，但新增映射字段，例如：
- `trade_theme_stage`
  - `launch/ferment` → `启动期`
  - `expand` → `加速期`
  - `climax` → `分歧高位`
  - `fade` → `退潮期`

#### 增强版
直接在聚合结果中输出：
- `theme_trade_stage`
- `theme_persistence_days`
- `theme_heat_trend`

### 验收标准
- 题材层输出更贴近交易话语体系
- 后续通知 / AI / 前端解释更一致

---

### 修正项 5：强化外部热点上下文与本地板块热度融合

**优先级：P1**

### 当前问题
OpenClaw 外部题材上下文已经接入，但在 `ThemePositionResolver` 的最终裁决中影响力仍不够强。

### 目标
让外部题材输入真正参与“主线/非主线”判断，而不只是作为增强信息。

### 主要文件
- `src/services/theme_position_resolver.py`
- `src/services/theme_aggregation_service.py`
- `src/services/theme_context_ingest_service.py`

### 建议改法
引入双源融合权重：
- 本地板块强度（盘面）
- 外部题材热度（语义热点）
- 置信度 / 匹配质量

可考虑新增：
- `external_theme_score`
- `blended_theme_score`
- `theme_source_consensus`

例如：
- 外部强 + 本地强 → `main_theme`
- 外部强 + 本地弱 → `secondary_theme / 观察`
- 外部弱 + 本地强 → `secondary_theme`
- 外部弱 + 本地弱 → `non_theme`

### 验收标准
- OpenClaw 热点输入对最终题材位置判断有可解释的影响
- 主线票识别更贴近盘前/盘中真实市场主线

---

### 修正项 6：将 AI 二筛从“解释器”推进为“裁判型结构化审查器”

**优先级：P1**

### 当前问题
当前流程仍是：
- 规则层先裁
- AI 再解释/归纳/轻纠偏

这使 AI 更像“结构化解释器”，而非真正的二筛裁判。

### 目标
让 AI 明确输出固定协议字段，并与规则层形成：
- 规则裁决
- AI 复审
- 差异对比
- 风险提示

### 主要文件
- `src/services/candidate_analysis_service.py`
- `src/services/ai_review_protocol.py`
- `api/v1/schemas/screening.py`

### 建议改法
#### 协议层面
新增/显式输出：
- `ai_environment_ok`
- `ai_theme_position`
- `ai_trade_stage`
- `ai_entry_maturity`
- `ai_risk_level`
- `ai_stop_loss`
- `ai_take_profit_plan`
- `ai_invalidation_rule`
- `ai_rule_conflict_flags`

#### 展示层面
增加“规则 vs AI”差异字段，便于人工判断：
- `rule_trade_stage`
- `ai_trade_stage`
- `stage_conflict`

### 验收标准
- AI 输出可结构化落库
- AI 的复审结果可被前端/通知直接消费
- 能清晰看到“AI 与规则是否一致”

---

### 修正项 7：清理 YAML 中残留的旧分析器语义

**优先级：P2**

### 当前问题
部分 YAML 元数据已完成归位，但 instructions 仍保留旧式分析器口吻，尤其：
- `bull_trend.yaml`
- 可能还有部分辅助策略 YAML

### 目标
让不同策略的说明文案与其系统角色一致：
- `stock_pool`：强调“入池/跟踪价值”
- `entry_core`：强调“买点类型/成熟度/结构确认”
- `observation`：强调“观察信号，不直接执行”

### 主要文件
- `strategies/bull_trend.yaml`
- `strategies/volume_breakout.yaml`
- `strategies/trendline_breakout.yaml`
- `strategies/bottom_volume.yaml`
- 其他相关 YAML

### 建议改法
重写 `instructions`，避免直接出现：
- “买入/减仓/卖出建议”
- “直接操作倾向”

转而改成：
- 入池依据
- 优先级解释
- 对后续层的支持作用

### 验收标准
- YAML 文案与 `system_role` 一致
- 新体系语义更统一，减少维护歧义

---

### 修正项 8：补充防回退测试

**优先级：P2**

### 当前问题
已有五层 E2E 测试，但缺少针对“规则收紧”的强约束测试。

### 目标
避免后续改动重新放宽口径。

### 主要文件
- `tests/test_e2e_five_layer_local.py`
- 建议新增：
  - `tests/test_candidate_pool_classifier.py`
  - `tests/test_trade_stage_judge_strict_gate.py`
  - `tests/test_theme_position_resolver_fusion.py`

### 建议增加的测试用例
1. `non_theme` 不得进入 `leader_pool`
2. `follower_theme` 不得进入 `add_on_strength`
3. `secondary_theme` 在 strict 模式下最高 `probe_entry`
4. 无止损锚点不得进入执行级
5. 外部热点缺失且本地板块弱时，主题位置不得判为 `main_theme`

### 验收标准
- 规则收紧后可通过测试固定下来
- 防止未来维护时重新放宽

---

## 四、建议实施顺序

### 第一阶段：门控收敛（建议先做）
1. 修改 `candidate_pool_classifier.py`
2. 修改 `trade_stage_judge.py`
3. 在 `screening_task_service.py` 五层链中补显式题材约束
4. 增补对应单元测试

### 第二阶段：题材层增强
1. 增强 `theme_position_resolver.py`
2. 增强 `sector_heat_engine.py` / `theme_aggregation_service.py`
3. 引入题材生命周期与双源融合

### 第三阶段：AI 二筛升级
1. 扩展 `ai_review_protocol.py`
2. 扩展 `candidate_analysis_service.py`
3. 扩展 API schema 和前端展示

### 第四阶段：策略语义清理
1. 清理 `strategies/*.yaml` 中旧分析器描述
2. 统一 `system_role` 导向文案

---

## 五、建议的阶段性结果定义

### 完成 P0 后，系统应达到：
- 非主线题材基本不能进入 `leader_pool`
- `add_on_strength` 候选显著更少、更纯
- 执行级候选更贴近真正主线龙头

### 完成 P1 后，系统应达到：
- 题材判断更稳定、更接近市场主线语言
- OpenClaw 热点输入不再只是辅助信息
- AI 二筛具备更强结构化复审能力

### 完成 P2 后，系统应达到：
- 文案、规则、结构统一
- 测试可防止回退
- 维护成本下降

---

## 六、一句话修正目标

> 把当前“已经长出五层骨架”的系统，进一步收紧成一套真正做到“先环境、再题材、再强势股、再买点、最后执行”的短线交易系统。

---

*写于 2026-04-08：作为 `daily_stock_analysis` 项目交易体系差异修正的执行清单，供后续分阶段开发使用。*
