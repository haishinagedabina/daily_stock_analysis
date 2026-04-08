# 五层交易系统回测重构最终实施方案

**日期**：2026-04-08  
**适用项目**：`daily_stock_analysis`  
**定位**：作为五层交易系统回测改造的最终实施基线，用于指导后续开发、评审、联调与旧系统替换。

---

## 一、目标与范围

本次改造的目标，不是继续增强旧版 advice backtest，而是直接建立一套：

> **以五层候选快照为事实源、面向 run 的五层交易系统回测子系统。**

新系统要评估的对象不再是：
- `AnalysisHistory.operation_advice`

而是：
- `screening_runs`
- `screening_candidates`
- 候选在决策当时的五层状态
- 候选对应的 `trade_plan_json`
- 不同类型信号在未来窗口下的后验表现

### 本期实施范围
- 仅覆盖 A 股长仓语境
- 仅覆盖日线级回测
- 支持 `historical_snapshot` / `rule_replay` / `parameter_calibration`
- 支持 `entry / exit / observation` 三类信号独立评估
- 支持 `conservative / baseline / optimistic` 三档执行模型
- 支持分组统计、稳定性指标与建议分级输出

### 本期不纳入范围
- 分钟级/分时级成交仿真
- 自动修改策略规则
- 多市场统一回测模型
- 复杂组合仓位仿真

---

## 二、现状基础与关键判断

当前仓库已经具备五层快照落库基础，核心字段已存在于：
- `screening_runs`
- `screening_candidates`

现有五层字段来源与保存位置可见：
- `src/storage.py`
- `src/services/screening_task_service.py`

当前已具备并可直接复用的关键字段包括：
- `market_regime`
- `theme_position`
- `candidate_pool_level`
- `setup_type`
- `entry_maturity`
- `trade_stage`
- `ai_trade_stage`
- `trade_plan_json`
- `factor_snapshot_json`
- `matched_strategies_json`
- `rule_hits_json`

这意味着：
- **新系统无需等待五层快照体系补齐后再启动**
- **新系统可以直接以 `screening_candidates` 为主事实入口实施**

---

## 三、总实施原则

### 原则 1：新系统以 `screening_candidates` 历史快照为唯一主事实源
新回测主链路不再以 `AnalysisHistory` 为入口。

### 原则 2：snapshot / replay / calibration 必须分离
三类模式都要支持，但不能混用语义、混做主结论。

### 原则 3：信号必须按 `entry / exit / observation` 分 evaluator
不得再用一套统一收益评分函数同时评估所有信号。

### 原则 4：执行模型必须独立建模
成交时点、成交价格、限价阻塞、gap 调整、模糊日线处理都必须结构化记录。

### 原则 5：新系统先保守、后增强
正式主结论默认建立在 `conservative` 执行模型之上。

### 原则 6：回测系统先产出建议，不自动改规则
建议输出必须分级，且要经过样本量、稳定性和复核闸门。

---

## 四、旧系统处理策略

旧 advice backtest 主链路不再演进，进入冻结状态；在新系统完成验收前仅保留短期兼容读能力，不再承担新功能，验收通过后移除。

### 冻结为 deprecated 的旧模块
- `src/core/backtest_engine.py`
- `src/services/backtest_service.py`
- `api/v1/endpoints/backtest.py`
- `api/v1/schemas/backtest.py`
- `src/agent/tools/backtest_tools.py`

### 处理原则
- 不再向旧链路追加功能
- 不再将旧结果表作为新系统扩展基础
- 新功能全部进入新命名空间

---

## 五、新系统总体架构

建议将新回测系统统一放入：

- `src/backtest/`
  - `models/`
  - `repositories/`
  - `services/`
  - `classifiers/`
  - `execution/`
  - `evaluators/`
  - `aggregators/`
  - `recommendations/`

### 职责划分

#### `models/`
承载回测运行、事实表、汇总表、校准结果、建议结果的 ORM。

#### `repositories/`
负责回测 run、evaluation、summary、recommendation 的持久化与查询。

#### `services/`
负责创建回测 run、编排候选选择、调用执行模型与 evaluator、保存结果。

#### `classifiers/`
负责将候选快照分类为 `entry / exit / observation`。

#### `execution/`
负责执行假设、成交解析、成交状态输出。

#### `evaluators/`
分别负责 Entry / Exit / Observation 三类信号的评价。

#### `aggregators/`
负责按 run、按单维度、按组合维度聚合，并生成稳定性指标。

#### `recommendations/`
负责建议分级、建议闸门与建议输出。

---

## 六、回测模式定义

### 1）`historical_snapshot`
使用历史真实落库的候选快照做评估。

**用途：**
- 评价线上系统过去真实表现
- 作为主结论依据

### 2）`rule_replay`
在统一历史数据上按新规则重跑。

**用途：**
- 新旧规则对比
- 规则实验验证

### 3）`parameter_calibration`
固定大框架，仅变参数做对比。

**用途：**
- 阈值校准
- 门控矩阵校准
- 权重敏感性对比

### 强制要求
每条 evaluation、summary、recommendation 都必须显式记录：
- `evaluation_mode`
- `execution_model`
- `snapshot_source`
- `replayed`

对于 replay / calibration 结果，必须支持区分：
- `snapshot_*`
- `replayed_*`

至少在模型字段或审计 JSON 中保留两套值，禁止只做“replay 打标”而不保留真实快照值与重演值差异。

---

## 七、数据源与数据口径

### 7.1 主输入
新系统主输入固定为：
- `screening_runs`
- `screening_candidates`

### 7.2 候选选择规则

#### `historical_snapshot`
- 只读取历史已持久化的候选快照字段
- 不允许用事后 enrich 结果替代原始快照
- 不允许用 replay 重算字段冒充真实快照

#### `rule_replay`
- 明确标记为 replay
- 允许使用统一历史数据按新规则生成候选评估结果

#### `parameter_calibration`
- 在 replay 框架上，仅改变参数
- 保持大框架与数据范围固定

### 7.3 行情输入
本期默认只使用日线级数据：
- OHLCV
- 涨停/跌停状态
- 停牌状态

后续扩展分钟级数据时，另开增强版本，不纳入本次实施。

### 7.4 必须显式区分的字段语义
- `known_at_decision_time`
- `derived_after_close`
- `replayed`
- `snapshot_source`
- `snapshot_*`
- `replayed_*`

这些字段不一定全部暴露给前端，但必须在模型或审计数据中可追踪。

---

## 八、核心数据模型设计

建议新增 5 张核心表。

### 8.1 `five_layer_backtest_runs`

用于记录一次回测任务的元信息。

#### 建议字段
- `id`
- `backtest_run_id`
- `evaluation_mode`
- `trade_date_from`
- `trade_date_to`
- `market`
- `execution_model`
- `engine_version`
- `rules_version`
- `data_version`
- `market_data_version`
- `theme_mapping_version`
- `candidate_snapshot_version`
- `candidate_filter_json`
- `config_json`
- `status`
- `sample_count`
- `completed_count`
- `error_count`
- `created_at`
- `completed_at`

### 8.2 `five_layer_backtest_evaluations`

作为新系统的候选级事实表。

#### 基础标识
- `id`
- `backtest_run_id`
- `screening_run_id`
- `screening_candidate_id`
- `trade_date`
- `code`
- `name`

#### 五层快照
- `snapshot_market_regime`
- `snapshot_theme_position`
- `snapshot_candidate_pool_level`
- `snapshot_setup_type`
- `snapshot_entry_maturity`
- `snapshot_trade_stage`
- `snapshot_ai_trade_stage`

#### replay / calibration 结果字段
- `replayed_market_regime`
- `replayed_theme_position`
- `replayed_candidate_pool_level`
- `replayed_setup_type`
- `replayed_entry_maturity`
- `replayed_trade_stage`
- `replayed_ai_trade_stage`

#### 回测元数据
- `evaluation_mode`
- `signal_family`
- `signal_type`
- `evaluator_type`
- `execution_model`
- `snapshot_source`
- `known_at_decision_time`
- `replayed`

#### 执行结果
- `entry_timing`
- `entry_price_basis`
- `entry_fill_status`
- `entry_fill_price`
- `exit_price_basis`
- `exit_fill_status`
- `exit_fill_price`
- `limit_blocked`
- `gap_adjusted`
- `ambiguous_intraday_order`
- `slippage_bps`
- `fee_bps`
- `tax_bps`

#### 指标与标签
- `forward_return_1d`
- `forward_return_3d`
- `forward_return_5d`
- `forward_return_10d`
- `mae_pct`
- `mfe_pct`
- `max_drawdown_pct`
- `max_upside_pct`
- `holding_days`
- `first_hit`
- `first_hit_day`
- `risk_avoided_pct`
- `opportunity_cost_pct`
- `stage_success`
- `plan_success`
- `signal_quality_score`
- `topk_hit_flag`
- `pool_rank_percentile`
- `relative_strength_bucket`

#### 扩展 JSON
- `trade_plan_json`
- `factor_snapshot_json`
- `diagnostics_json`
- `evaluation_reason_json`

### 8.3 `five_layer_backtest_group_summaries`

用于承载分组聚合结果。

#### 建议字段
- `id`
- `backtest_run_id`
- `group_type`
- `group_key`
- `group_key_json`
- `sample_count`
- `win_rate_pct`
- `avg_return_pct`
- `median_return_pct`
- `p25_return_pct`
- `p75_return_pct`
- `avg_mae_pct`
- `avg_mfe_pct`
- `avg_drawdown_pct`
- `profit_loss_ratio`
- `stability_score`
- `extreme_sample_ratio`
- `metrics_json`
- `created_at`

### 8.4 `five_layer_backtest_calibration_outputs`

用于记录规则/参数校准输出。

#### 建议字段
- `id`
- `backtest_run_id`
- `target_scope`
- `target_key`
- `experiment_type`
- `baseline_config_json`
- `candidate_config_json`
- `delta_metrics_json`
- `decision`
- `confidence_level`
- `created_at`

### 8.5 `five_layer_backtest_recommendations`

用于记录建议结果。

#### 建议字段
- `id`
- `backtest_run_id`
- `recommendation_type`
- `target_scope`
- `target_key`
- `current_rule`
- `suggested_change`
- `sample_count`
- `primary_metrics_json`
- `stability_metrics_json`
- `confidence_level`
- `validation_status`
- `recommendation_level`
- `created_at`

### 8.6 索引与约束

重点索引：
- `backtest_run_id`
- `screening_candidate_id`
- `trade_date + code`
- `group_type + group_key`
- `signal_family + evaluation_mode`
- `recommendation_level + target_scope`

重点约束：
- `backtest_run_id` 唯一
- 单 run 内 `screening_candidate_id` 不重复评估

---

## 九、核心流程设计

单次回测运行流程固定为：

1. 创建 `five_layer_backtest_run`
2. 根据 `evaluation_mode` 选择候选快照
3. `SignalClassifier` 输出 `signal_family / signal_type / evaluator_type`
4. 读取 forward bars 与执行约束数据
5. `ExecutionModelResolver` 产生成交结果
6. 对应 evaluator 生成 candidate-level evaluation
7. 批量写入 `five_layer_backtest_evaluations`
8. `SummaryAggregator` 生成 overall / group / combo summaries
9. 如配置开启，再产出 calibration outputs 与 recommendations

---

## 十、信号分类设计

### 核心要求
- 不再依赖 `operation_advice` 文本关键词作为主分类依据
- 优先基于五层字段和 `trade_plan_json`

### 初版分类规则建议

#### `entry`
- `probe_entry`
- `add_on_strength`
- 其他明确执行级入场信号

#### `observation`
- `watch`
- `focus`
- `stand_aside`
- 无执行级 trade plan 的观察状态

#### `exit`
- 本期如 `trade_plan` 或后续规则中存在明确退出/减仓结构，则归为 `exit`
- 若当前候选快照里缺乏成熟退出信号，则本期先落地：
  - `ExitSignalEvaluator` 接口
  - schema
  - 样例测试
  - pipeline 挂点
- 待退出型样本源明确后，再将 exit evaluator 从“框架可用”升级为“生产启用”

### 实施要求
先实现独立的 `SignalClassifier`，避免分类逻辑散落在 service 中。

---

## 十一、执行模型设计

### 支持三档执行模型
- `conservative`
- `baseline`
- `optimistic`

### 使用规则
- `historical_snapshot` 默认 `conservative`
- 日常运营分析可选 `baseline`
- `optimistic` 仅做研究，不得作为主优化依据

### `ExecutionModelResolver` 必须输出
- `entry_fill_status`
- `entry_fill_price`
- `exit_fill_status`
- `exit_fill_price`
- `limit_blocked`
- `gap_adjusted`
- `ambiguous_intraday_order`

### 日线阶段必须实现的现实约束
- 收盘后确认信号不得按当天收盘成交
- 一字涨停买不到
- 一字跌停卖不掉
- gap 跳空穿越止损按更差价处理
- 同日止盈止损双触发按保守结果处理

### 本期边界
本期只做日线级执行模型，不引入分钟线成交仿真。

---

## 十二、三类 evaluator 设计

### 12.1 `EntrySignalEvaluator`

#### 评估重点
- `forward_return_1d/3d/5d/10d`
- `mae_pct`
- `mfe_pct`
- `max_drawdown_pct`
- `holding_days`
- `plan_success`
- `signal_quality_score`

#### 解决的问题
- 入场值不值得做
- 盈亏比是否合理
- 回撤是否可接受

### 12.2 `ExitSignalEvaluator`

#### 评估重点
- `risk_avoided_pct`
- `opportunity_cost_pct`
- 卖出后回撤规避
- 卖出后继续上涨幅度

#### 解决的问题
- 卖出是在保护利润还是错杀

### 12.3 `ObservationSignalEvaluator`

#### 评估重点
- 强行入场对照收益
- 强行入场对照回撤
- 后续转化为更成熟信号的概率
- 观望避免错误出手的比例

#### 解决的问题
- 观望是在错失机会，还是在避免低质量时机

### 统一要求
- 三类 evaluator 输出统一 schema
- 三类 evaluator 不共享同一主评分函数

---

## 十三、统计与建议层设计

### 13.1 聚合层级

#### overall summary
按 run 聚合：
- sample count
- avg / median return
- win rate
- avg mae / mfe
- avg drawdown
- top-k 命中率
- 候选池超额收益
- 分层排序一致性

#### 单维度 summary
至少支持：
- `market_regime`
- `theme_position`
- `candidate_pool_level`
- `setup_type`
- `entry_maturity`
- `trade_stage`
- `signal_family`

#### 组合 summary
首批支持：
- `theme_position + setup_type`
- `candidate_pool_level + entry_maturity`
- `market_regime + signal_family`

### 13.1.1 排序有效性优先
在五层系统中，聚合层不只服务于“交易收益观察”，还必须先验证：
- `leader_pool` 是否真的强于 `watchlist`
- `main_theme` 是否真的强于 `non_theme`
- `HIGH maturity` 是否真的强于 `MEDIUM / LOW`

因此 summary 层必须优先提供：
- Top-K 命中率
- 候选池超额收益
- 分层排序一致性

不能只输出收益均值而缺失排序有效性视角。

### 13.2 稳定性指标
至少实现：
- `median`
- `p25`
- `p75`
- `stddev`
- `extreme_sample_ratio`
- `time_bucket_stability`

### 13.3 建议引擎

建议分三级：
- `observation`
- `hypothesis`
- `actionable`

生成 `actionable` 的前提：
- 样本量达标
- 主指标方向一致
- 稳定性达标
- 归因相对清晰
- 已经通过 replay / calibration 复核

### 13.4 红线
- 不基于小样本直接生成 `actionable`
- 不基于单一指标直接推规则变更
- 不基于 `optimistic` 结果生成主优化建议

---

## 十四、API 与对外接口设计

新 API 保持 `/api/v1/backtest` 命名，但语义切到 run-based 模型。

### 建议接口
- `POST /api/v1/backtest/run`
- `GET /api/v1/backtest/runs/{backtest_run_id}`
- `GET /api/v1/backtest/runs/{backtest_run_id}/evaluations`
- `GET /api/v1/backtest/runs/{backtest_run_id}/summaries`
- `GET /api/v1/backtest/runs/{backtest_run_id}/calibration`
- `GET /api/v1/backtest/runs/{backtest_run_id}/recommendations`

### 返回原则
- 不再以旧 `overall / stock` summary 为主语义
- 所有结果以 `backtest_run_id` 为主索引

---

## 十五、Agent Tools 与 Web 迁移

### Agent Tools
建议重写为：
- `get_backtest_run_summary`
- `get_backtest_group_summary`
- `get_backtest_recommendations`
- `get_candidate_backtest_detail`

### Web 迁移
需要同步迁移：
- `apps/dsa-web/src/api/backtest.ts`
- `apps/dsa-web/src/types/backtest.ts`

### 原则
- 不维持旧 overall/stock summary 的长期兼容
- Phase 4 完成时，Web 与 Agent 必须全部切换到新 run-based 语义

---

## 十六、分阶段落地方案

### Phase 0：冻结旧系统并锁定字段合同

#### 目标
- 旧 backtest 停止演进
- 新系统字段、模式、分类、执行模型合同定版

#### 完成条件
- deprecated 范围明确
- 新表字段与索引清单明确
- `signal_family` 初版映射定版

### Phase 1：新模型、repository、service skeleton

#### 目标
- 建立新表
- 建立 run/evaluation/summary/recommendation repository
- 建立 `FiveLayerBacktestService` 骨架

#### 完成条件
- 能创建空 run
- 能选择候选样本
- 能写入空 evaluation 骨架

### Phase 2：核心评估链路

#### 目标
- 完成 `SignalClassifier`
- 完成 `ExecutionModelResolver`
- 完成 Entry / Exit / Observation 三类 evaluator
- 串起 candidate-level evaluation pipeline

#### 完成条件
- 指定区间可跑出一批 evaluation records
- 不依赖旧 `AnalysisHistory`
- 单测覆盖关键执行场景
- Exit evaluator 至少完成接口、schema、样例测试和 pipeline 挂点
- 如退出型样本源未定，允许 Phase 2 不在生产 run 中启用 exit 评估

### Phase 3：summary、稳定性、calibration、recommendation

#### 目标
- 建立整体/分组/组合 summary
- 建立样本门槛和稳定性指标
- 建立 calibration output
- 建立 recommendation engine

#### 完成条件
- summary 能支持五层维度与组合分析
- recommendation 有样本量和稳定性闸门

### Phase 4：API / Web / Agent 切换与旧系统移除

#### 目标
- 重写 backtest API
- 重写 agent tools
- 迁移 Web 调用
- 移除旧 backtest 读写主链路

#### 完成条件
- 项目中只保留一套 backtest 主链路
- API / Web / Agent 全部切换到新 run-based 语义

---

## 十七、验收标准

以下条件全部满足后，才允许替换旧系统：

1. 新链路主输入完全切到 `screening_candidates`
2. `historical_snapshot / rule_replay / parameter_calibration` 明确分离
3. `entry / exit / observation` 确实分 evaluator
4. `conservative` 执行模型样例测试通过
5. summary 支持五层分组与组合分析
6. recommendation 具备样本量与稳定性闸门
7. API / Web / Agent 全部切换到新 run-based 模型
8. 旧 `backtest_results / backtest_summaries` 不再有主写入路径

---

## 十八、一句话定版结论

> 最终实施方式就是：以 `screening_candidates` 历史快照为唯一主事实源，围绕“候选评估事实表 + 三类信号评估器 + 保守执行模型 + 分组统计与建议引擎”重建一套 run-based 五层回测子系统，再整体替换旧 advice backtest。

---

*写于 2026-04-08：用于作为 `daily_stock_analysis` 项目五层交易系统回测重构的最终实施方案与开发基线。*
