# 五层回测重构开发任务拆解方案

**日期**：2026-04-08  
**适用项目**：`daily_stock_analysis`  
**前提**：旧版 advice backtest 主链路进入冻结状态；在新系统完成验收前仅保留短期兼容读能力，不再承担新功能，验收通过后整体移除。

---

## 一、文档目的

本文件不是继续讨论原则，而是把《五层交易系统回测重构实施设计方案》拆成：

- 可分阶段执行的开发任务
- 每阶段明确交付物
- 每阶段明确风险点
- 每阶段明确验收标准

目标是让后续开发可以直接按 phase / PR / task 推进，而不是继续停留在抽象设计层。

---

## 二、总实施策略

建议采用：

> **先建新系统骨架 → 再接核心评估能力 → 再接统计与建议层 → 最后移除旧系统**

而不是：
- 一边修旧 backtest
- 一边塞新逻辑
- 最后变成混合系统

### 总体阶段建议
- **Phase 0：重构准备与冻结旧系统**
- **Phase 1：新数据模型与基础骨架**
- **Phase 2：核心评估链路（signal + execution + evaluators）**
- **Phase 3：统计、校准、建议输出**
- **Phase 4：API / Agent Tools / 旧系统清理**

---

## 三、Phase 0：重构准备与旧系统冻结

### 目标
正式切换团队认知：
- 旧版 backtest 不再演进
- 新回测系统另起主链路

### 任务
#### 0.1 冻结旧 backtest 模块
- 标记旧模块为 deprecated：
  - `src/core/backtest_engine.py`
  - `src/services/backtest_service.py`
  - `api/v1/endpoints/backtest.py`
  - `api/v1/schemas/backtest.py`
  - `src/agent/tools/backtest_tools.py`
- 禁止再向旧 backtest 追加新特性

#### 0.2 明确新回测命名空间
建议新代码集中到：
- `src/backtest/`
  - `models/`
  - `repositories/`
  - `services/`
  - `evaluators/`
  - `execution/`
  - `aggregators/`
  - `recommendations/`

#### 0.3 确认五层信号分类映射规则
先定一版 `signal_family` 分类表：
- 哪些 setup/stage 属于 `entry`
- 哪些属于 `exit`
- 哪些属于 `observation`

### 交付物
- 新目录结构方案
- deprecated 说明
- 初版 signal family mapping 文档或代码常量表

### 风险
- 团队成员误继续改旧 backtest
- 新旧路径混淆

### 验收标准
- 新回测工作全部进入新命名空间
- 旧 backtest 不再接受 feature 增量

---

## 四、Phase 1：新数据模型与基础骨架

### 目标
搭好新系统最小可运行骨架，但先不追求完整回测能力。

---

## 4.1 数据模型任务

### 任务 1：新增 ORM 表
新增以下模型：
- `FiveLayerBacktestRun`
- `FiveLayerBacktestEvaluation`
- `FiveLayerBacktestGroupSummary`
- `FiveLayerBacktestCalibrationOutput`
- `FiveLayerBacktestRecommendation`

### 任务 1.1：补齐 run 级版本字段
至少包含：
- `data_version`
- `market_data_version`
- `theme_mapping_version`
- `candidate_snapshot_version`

### 任务 1.2：补齐 snapshot / replay 双轨字段
evaluation 模型必须支持：
- `snapshot_*`
- `replayed_*`

至少对五层关键字段保留两套值，禁止仅靠 `replayed=true/false` 打标。

### 任务 2：补充索引与唯一约束
重点索引：
- `backtest_run_id`
- `screening_candidate_id`
- `trade_date + code`
- `group_type + group_key`
- `recommendation_level + target_scope`

### 任务 3：定义 JSON 字段边界
明确哪些数据放结构化列，哪些进入 JSON：
- 结构化列：查询/过滤/聚合频繁的字段
- JSON：解释性、扩展性字段

### 任务 3.1：定义时间一致性与审计字段
至少明确：
- `known_at_decision_time`
- `derived_after_close`
- `snapshot_source`
- `replayed`

### 交付物
- ORM 模型代码
- 数据库 migration 或 inline migration 方案

### 验收标准
- 新表可创建
- 可插入最小测试数据
- 索引设计支持后续查询

---

## 4.2 Repository 层任务

### 任务 4：创建新 repository
建议新增：
- `five_layer_backtest_repo.py`
- 或拆分为：
  - `run_repo.py`
  - `evaluation_repo.py`
  - `summary_repo.py`
  - `recommendation_repo.py`

### 任务 5：实现最小 CRUD
至少支持：
- 创建 backtest run
- 批量写入 evaluations
- 写入 group summaries
- 写入 calibration outputs
- 写入 recommendations
- 查询 run metadata
- 查询单 run evaluations

### 交付物
- repository 基础类
- 最小单元测试

### 验收标准
- 能独立对新表做增删改查
- 不依赖旧 backtest repo

---

## 4.3 Service 骨架任务

### 任务 6：创建 `FiveLayerBacktestService`
先实现最小骨架：
- `create_run()`
- `select_candidates()`
- `save_evaluations()`
- `compute_summaries()`（先空实现也可）

### 任务 7：定义 run config schema
例如：
- `mode`
- `trade_date_from`
- `trade_date_to`
- `market`
- `execution_model`
- `candidate_filters`
- `generate_recommendations`

### 任务 7.1：明确候选读取口径
必须明确：
- `historical_snapshot` 是否只读取原始快照字段
- 是否禁止使用 enrich 后验结果替代快照
- `rule_replay / parameter_calibration` 如何保留与快照值的差异

### 交付物
- service 骨架
- config dataclass / schema

### 验收标准
- 能创建一条空 run
- 能读取候选样本并生成空 evaluation 流程骨架

---

## 五、Phase 2：核心评估链路

### 目标
让新系统具备真正“可用”的候选级评估能力。

---

## 5.1 SignalClassifier

### 任务 8：实现 `SignalClassifier`
输入：
- screening candidate
- trade_plan
- ai fields

输出：
- `signal_family`
- `signal_type`
- `evaluator_type`

### 实施要求
- 不能再依赖 `operation_advice` 文本关键词作为主分类依据
- 必须优先基于五层字段和 trade plan 结构

### 验收标准
- 对典型 candidate 样本能稳定分到 entry/exit/observation
- 有单测覆盖典型 setup/stage 组合

---

## 5.2 ExecutionModelResolver

### 任务 9：实现执行模型解析器
支持：
- `conservative`
- `baseline`
- `optimistic`

### 必须处理的规则
- 收盘后信号不得按当天收盘成交
- 涨停买不到
- 跌停卖不掉
- gap 跳空处理
- 同日双触发保守处理

### 输出字段
- `entry_fill_status`
- `entry_fill_price`
- `exit_fill_status`
- `exit_fill_price`
- `limit_blocked`
- `gap_adjusted`
- `ambiguous_intraday_order`

### 验收标准
- 单测覆盖：
  - 一字涨停买不到
  - 一字跌停卖不掉
  - gap down 跳空止损
  - 同日止盈止损双触发

---

## 5.3 Entry / Exit / Observation 三类 evaluator

### 任务 10：实现 `EntrySignalEvaluator`
评估重点：
- forward returns
- MAE / MFE
- drawdown
- holding days
- 是否值得做

### 任务 11：实现 `ExitSignalEvaluator`
评估重点：
- risk avoided
- opportunity cost
- 卖出后回撤
- 卖出后继续上涨幅度

#### 本期边界
- 若当前退出型候选快照来源不足，则 Phase 2 先完成：
  - evaluator 接口
  - schema
  - 样例测试
  - pipeline hook
- 待退出型样本源明确后，再升级为生产启用能力

### 任务 12：实现 `ObservationSignalEvaluator`
评估重点：
- 避免错误出手比例
- 等待后转化为更成熟信号的概率
- 强行入场对照表现

### 实施要求
- 三类 evaluator 输出统一 evaluation result schema
- 但内部主指标允许不同

### 验收标准
- 三类 evaluator 各自有单测
- 不存在“一套评分逻辑吃所有信号”的情况
- Exit evaluator 至少具备可测试框架，不强行要求本期就有完整生产样本源

---

## 5.4 Candidate-level evaluation pipeline

### 任务 13：串起完整评估链路
流程：
1. 读取 candidate 快照
2. 信号分类
3. 读取 forward bars
4. 解析执行模型
5. 调 evaluator
6. 生成 evaluation record
7. 批量写库

### 交付物
- 可运行的新回测最小主流程

### 验收标准
- 指定时间区间可跑出一批 evaluation records
- 不依赖旧 `AnalysisHistory` 作为主输入
- `historical_snapshot / rule_replay / parameter_calibration` 结果可区分

---

## 六、Phase 3：统计、校准、建议输出

### 目标
在候选级评估事实表之上，建立真正能支持系统优化的上层能力。

---

## 6.1 Group Summary Aggregator

### 任务 14：实现 overall summary
按 run 聚合：
- sample count
- avg / median return
- win rate
- avg mae / mfe
- drawdown
- top-k 命中率
- 候选池超额收益
- 分层排序一致性

### 任务 15：实现按单维度分组 summary
按以下维度聚合：
- `market_regime`
- `theme_position`
- `candidate_pool_level`
- `setup_type`
- `entry_maturity`
- `trade_stage`
- `signal_family`

### 任务 16：实现 combo summary
支持组合键：
- `theme_position + setup_type`
- `candidate_pool_level + entry_maturity`
- `market_regime + signal_family`
- 后续可扩展更多组合

### 任务 16.1：实现排序有效性指标
至少覆盖：
- `leader_pool vs watchlist`
- `main_theme vs non_theme`
- `HIGH vs MEDIUM / LOW maturity`

优先回答“分层是否有效”，再回答“收益放大了多少”。

### 验收标准
- summary 不再局限 overall / stock
- group_type / group_key 可支持筛选查询

---

## 6.2 Stability & sample quality metrics

### 任务 17：补充分布与稳定性指标
至少实现：
- median
- p25 / p75
- extreme sample ratio
- time-bucket stability

### 任务 18：样本门槛机制
建立规则：
- 低于观察门槛：仅展示
- 低于建议门槛：不得生成 actionable recommendation

### 任务 18.1：补充稳定性与可追溯性闸门
建议增加：
- 时间分桶稳定性
- 极端样本占比
- recommendation evidence 可回溯到 evaluation / summary 样本

### 验收标准
- summary 中可看到稳定性相关指标
- recommendation engine 会读取样本门槛

---

## 6.3 Calibration outputs

### 任务 19：实现 calibration output 生成器
适用于：
- 参数试验
- 规则变体对比

### 输出内容
- baseline config
- candidate config
- delta metrics
- decision
- confidence level

### 验收标准
- snapshot run 与 calibration run 输出能明确区分

---

## 6.4 Recommendation engine

### 任务 20：实现 recommendation 分级引擎
输出级别：
- `observation`
- `hypothesis`
- `actionable`

### 任务 21：实现建议闸门
必须检查：
- 样本量
- 主指标一致性
- 稳定性
- replay / calibration 验证状态

### 验收标准
- 不会基于低样本直接生成 actionable
- recommendation 可追溯到 group summary / evaluation evidence

---

## 七、Phase 4：API、Agent Tools、旧系统清理

### 目标
对外接口切换到新回测系统，并移除旧实现。

---

## 7.1 API 重写

### 任务 22：重写 run API
建议实现：
- `POST /api/v1/backtest/run`

### 任务 23：新增 run detail API
- `GET /api/v1/backtest/runs/{backtest_run_id}`

### 任务 24：新增 evaluations 查询 API
- `GET /api/v1/backtest/runs/{backtest_run_id}/evaluations`

### 任务 25：新增 summaries 查询 API
- `GET /api/v1/backtest/runs/{backtest_run_id}/summaries`

### 任务 26：新增 calibration 查询 API
- `GET /api/v1/backtest/runs/{backtest_run_id}/calibration`

### 任务 27：新增 recommendations 查询 API
- `GET /api/v1/backtest/runs/{backtest_run_id}/recommendations`

### 验收标准
- API 返回结构完全切换到新 schema
- 不再暴露旧 overall/stock 旧语义为主接口

---

## 7.2 Agent Tools 重写

### 任务 28：重写 backtest agent tools
建议新工具：
- `get_backtest_run_summary`
- `get_backtest_group_summary`
- `get_backtest_recommendations`
- `get_candidate_backtest_detail`

### 验收标准
- agent tool 能基于新 run_id 读取结构化回测结果
- 不再依赖旧 overall summary

---

## 7.3 旧系统删除

### 前置条件
- 新系统完成验收
- Web / Agent / API 已切换
- 旧链路不再承载新功能

### 任务 29：删除旧 backtest 代码
候选删除对象：
- `src/core/backtest_engine.py`
- `src/services/backtest_service.py`
- 旧 `api/v1/endpoints/backtest.py`
- 旧 `api/v1/schemas/backtest.py`
- 旧 `src/agent/tools/backtest_tools.py`
- 旧 backtest tests

### 任务 30：移除旧表写入与读路径
- 不再写入 `backtest_results`
- 不再写入 `backtest_summaries`
- 后续可删除旧表 migration

### 验收标准
- 项目中只保留一套 backtest 主链路
- 不存在新旧语义混杂

---

## 八、建议的 PR 拆分方式

为了控制风险，建议不要一个超大 PR 直接上全部内容。

### PR-1：新数据模型 + repository + service skeleton
### PR-2：SignalClassifier + ExecutionModelResolver
### PR-3：Entry / Exit / Observation evaluators
### PR-4：evaluation pipeline + write path
### PR-5：summary / calibration / recommendation engines
### PR-6：API + schemas + agent tools
### PR-7：删除旧 backtest 代码和旧表路径

这样能保证每个阶段都能单独 review。

---

## 九、建议优先顺序（如果资源有限）

如果必须控制开发范围，我建议优先级如下：

### 必须先做
1. 新 ORM 模型
2. SignalClassifier
3. ExecutionModelResolver
4. Entry / Exit / Observation evaluator
5. candidate-level evaluation pipeline

### 第二批
6. group summary
7. stability metrics
8. recommendation engine

### 最后
9. calibration outputs
10. agent tool 完整增强
11. 旧系统彻底清理

---

## 十、每阶段完成后的“闸门问题”

每完成一个 phase，建议都问这几个问题：

### Phase 1 完成后
- 新表是否足以承载五层回测事实？
- 有没有偷偷沿用旧语义？

### Phase 2 完成后
- 买入 / 卖出 / 观望是否真的分 evaluator？
- 执行模型是否真的结构化，而不是隐藏在逻辑里？

### Phase 3 完成后
- summary 是否能支持规则优化，而不只是展示数据？
- recommendation 是否已经有样本量和稳定性闸门？

### Phase 4 完成后
- 项目里是否只剩一套 backtest 主链路？
- API 和 agent tool 是否已完全切换到新语义？

---

## 十一、一句话结论

> 五层回测重构的正确实施方式，不是围绕旧模块补丁式推进，而是按“新模型 → 新评估链路 → 新统计与建议层 → 替换旧接口与删除旧系统”的顺序分阶段落地；只要按这个拆解走，项目就能从旧版建议回测平滑进入真正面向五层交易系统的回测子系统。

---

*写于 2026-04-08：用于把五层交易系统回测重构方案进一步拆解为可执行的开发阶段、交付物和验收标准。*
