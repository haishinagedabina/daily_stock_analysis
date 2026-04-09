# 五层回测重构实施启动清单

**日期**：2026-04-08  
**适用项目**：`daily_stock_analysis`  
**配套主文档**：`docs/five-layer-backtest-rebuild-development-breakdown-2026-04-08.md`

---

## 一、用途说明

这不是设计文档，而是**开工前和实施中的一页式执行清单**。

目标只有一个：

> 让开发团队在真正进入五层回测重构时，不偏离既定实施方案，不跳过关键护栏，不把项目重新做回“旧版 advice backtest 的增强版”。

---

## 二、开工前总原则

在任何编码开始前，团队必须先确认以下 4 条：

- [ ] **旧 backtest 的定位已经冻结**：旧系统只作为兼容层 / baseline，不再承担新功能演进
- [ ] **新回测主链路将以 `screening_candidates` 和五层字段为中心**，不是继续围绕 `AnalysisHistory` 文本建议做增强
- [ ] **snapshot / replay / calibration 是三种不同模式**，不能混用
- [ ] **recommendation engine 只产出建议，不自动改规则/改阈值/改参数**

如果以上任意一条未达成共识，**不得开工**。

---

## 三、Phase -1：现状勘查与迁移前审计清单

### 3.1 旧系统依赖盘点
- [ ] 已盘点旧 backtest service / repo / API / agent tool 的调用入口
- [ ] 已盘点 Web / API / Agent / tests 中对旧 backtest 的依赖点
- [ ] 已确认是否存在内部脚本、定时任务、临时工具直接依赖旧 backtest 输出

### 3.2 数据源盘点
- [ ] 已确认 `screening_runs` 可用
- [ ] 已确认 `screening_candidates` 可用
- [ ] 已确认五层字段快照完整度
- [ ] 已确认 forward bars 数据来源与完整度
- [ ] 已确认旧 `AnalysisHistory` 不再作为新主链路输入，只保留兼容/对照用途

### 3.3 可观测性与版本盘点
- [ ] 已确认当前数据版本字段来源
- [ ] 已确认当前日志/trace 是否足够支持新回测问题排查
- [ ] 已列出新 run-based 回测需要新增的审计日志

### 3.4 风险清单
- [ ] 已输出 API 契约切换风险
- [ ] 已输出 Web / Agent 切换风险
- [ ] 已输出历史数据缺口风险
- [ ] 已输出 snapshot / replay 混用风险
- [ ] 已输出旧系统删除过早风险

### Phase -1 完成标准
- [ ] 已形成：入口清单 / 依赖清单 / 数据可用性清单 / 缺口清单 / 风险清单
- [ ] 团队已确认：可以进入 Phase 0 / Phase 1

---

## 四、实施红线（任何阶段都不能破）

### 4.1 快照真实性红线
- [ ] `historical_snapshot` 模式下，所有决策字段必须来自决策当时已持久化的快照
- [ ] 当时没保存的字段，允许为空，但**不得**用 replay/calibration 结果回填冒充 snapshot
- [ ] snapshot / replay / calibration 结果必须在存储、查询、API 中可明确区分
- [ ] 禁止在 summary 中 silent merge 不同模式结果，除非显式声明口径

### 4.2 信号评估红线
- [ ] 买入、卖出、观望必须分 evaluator，不允许重新压成一套统一评分器
- [ ] 不允许重新退化成 `long/cash` 二元语义主导的新系统
- [ ] 不允许把 `operation_advice` 文本作为新主回测入口

### 4.3 执行模型红线
- [ ] 不允许默认把收盘后信号按当日收盘成交
- [ ] 不允许忽略涨停买不到 / 跌停卖不掉
- [ ] 不允许忽略 gap 跳空影响
- [ ] 不允许回避同日双触发的不确定性处理

### 4.4 建议引擎红线
- [ ] recommendation engine 不得直接修改生产规则
- [ ] recommendation engine 不得自动调参数/改阈值
- [ ] 所有 actionable recommendation 都必须有证据链并经过人工审核或独立复核

### 4.5 旧系统处理红线
- [ ] 在新系统未完成验收前，不得提前删除旧 backtest 主链路
- [ ] 在 Web / API / Agent 未全部切换前，不得移除旧接口读路径

---

## 五、Phase 1 开工清单：新模型与骨架

- [ ] 已创建 `src/backtest/` 新命名空间
- [ ] 已新增 5 张核心表 ORM
- [ ] 已补齐 run 级版本字段
- [ ] 已补齐 `snapshot_* / replayed_*` 双轨字段
- [ ] 已建 repository skeleton
- [ ] 已建 `FiveLayerBacktestService` skeleton
- [ ] 已确认 schema 足以表达五层回测事实，而不是旧 overall/stock 语义翻版

### Phase 1 最小验证
- [ ] 能创建空 run
- [ ] 能写入最小 evaluation 占位记录
- [ ] 新表索引 / 唯一约束 / 字段合同通过检查

---

## 六、Phase 2 开工清单：核心评估链路

- [ ] 已实现 `SignalClassifier`
- [ ] 已明确 `entry / exit / observation` 分类映射
- [ ] 已实现 `ExecutionModelResolver`
- [ ] 已实现 `conservative / baseline / optimistic`
- [ ] 已实现 `EntrySignalEvaluator`
- [ ] 已实现 `ObservationSignalEvaluator`
- [ ] 已为 `ExitSignalEvaluator` 建好接口 / schema / 样例测试 / pipeline hook
- [ ] 已串起 candidate-level evaluation pipeline

### Phase 2 特别检查
- [ ] `historical_snapshot` 读取口径没有被 enrich/replay 污染
- [ ] Entry / Exit / Observation 没有被重新写回同一套评分函数
- [ ] Exit evaluator 若样本源仍不足，已明确标记为**非生产结论引擎**

### Phase 2 最小验证
- [ ] 已通过 snapshot vs replay 最小 smoke
- [ ] 已通过执行模型边界 smoke（涨停/跌停/gap/双触发）
- [ ] 指定区间已能跑出一批 evaluation records

---

## 七、Phase 3 开工清单：统计、校准、建议输出

- [ ] 已实现 overall / 单维度 / combo summary
- [ ] 已实现排序有效性指标
- [ ] 已实现中位数 / 分位数 / 极端样本占比 / 时间分桶稳定性
- [ ] 已实现样本门槛机制
- [ ] 已实现 calibration output 生成器
- [ ] 已实现 recommendation 分级引擎
- [ ] 已实现 recommendation evidence 可回溯链路

### Phase 3 特别检查
- [ ] recommendation 只输出建议，不自动改规则
- [ ] 小样本结果不会直接给 actionable
- [ ] summary 可以解释“为什么有效/无效”，而不只是展示收益均值

### Phase 3 最小验证
- [ ] summary 与 evidence 可回溯
- [ ] recommendation 闸门可工作
- [ ] snapshot run 与 calibration run 的输出可明确区分

---

## 八、Phase 4 开工清单：接口切换与旧系统清理

- [ ] 已重写 run API / detail API / evaluations API / summaries API / calibration API / recommendations API
- [ ] 已重写 backtest agent tools
- [ ] 已确认 Web / Agent / API 都能读新 run-based 结果
- [ ] 已完成新旧系统对照验证
- [ ] 已完成残留引用清点
- [ ] 已确认旧链路不再承载新功能

### Phase 4 特别检查
- [ ] 没有继续暴露旧 overall/stock 语义作为主接口
- [ ] 没有隐藏依赖仍指向旧 backtest 表或旧 service
- [ ] 旧系统删除动作发生在切换验证之后，而不是之前

### Phase 4 最小验证
- [ ] API / Web / Agent 合同 smoke 通过
- [ ] 新旧结果对照完成
- [ ] 删除旧系统前完成残留引用排查

---

## 九、PR 执行纪律

每个 PR 都必须回答以下问题：

- [ ] 这个 PR 只覆盖当前阶段范围，没有夹带无关重构
- [ ] 补了对应测试，不靠文字解释代替验证
- [ ] 明确说明 snapshot / replay / calibration 是否受影响
- [ ] 明确说明是否影响 API / Web / Agent
- [ ] 没有绕开执行模型、样本门槛、稳定性约束

---

## 十、出现以下情况时，必须暂停实施并回审方案

如果出现以下任一情况，应立即暂停，而不是继续堆代码：

- [ ] 发现 snapshot 字段历史上根本没保存，且团队想用 replay 结果回填顶上
- [ ] 发现 Exit 样本源严重不足，但团队仍想把 Exit evaluator 标记为生产可用
- [ ] 发现 recommendation 想直接联动规则配置自动修改
- [ ] 发现 Web / Agent 仍严重依赖旧 backtest，但清理计划不明确
- [ ] 发现 summary 指标很多，但无法回溯到 evaluation evidence
- [ ] 发现开发顺序已经跳过 smoke / 验证闸门，直接进入大区间回放或接口切换

---

## 十一、一句话启动结论

> 五层回测重构可以直接实施，但必须按“先审计、再骨架、再评估链路、再统计建议层、最后切接口和删旧系统”的顺序推进，并把 snapshot 真实性、执行模型现实性、recommendation 权限边界当作不可突破的硬护栏。
