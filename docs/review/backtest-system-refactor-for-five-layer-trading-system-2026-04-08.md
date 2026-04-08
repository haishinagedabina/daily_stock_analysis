# 回测系统重构方案：面向当前五层交易系统的回测与迭代优化闭环

**日期**：2026-04-08  
**适用项目**：`daily_stock_analysis`  
**目标**：将当前“面向分析建议文本”的回测系统，重构为“面向五层交易体系决策链”的回测与优化系统，使其能够持续提升：

- 选股准确率
- 主线题材识别准确率
- 强势股池质量
- 买点识别准确率
- 买卖点/阶段建议准确率
- 风险控制与交易计划质量

---

## 一、为什么必须重构当前回测系统

当前回测系统的核心逻辑是：

1. 从 `AnalysisHistory` 读取历史分析记录
2. 从 `operation_advice` 文本推断方向：
   - 买入 / 卖出 / 持有 / 观望
3. 用未来 N 天价格表现判断：
   - 方向是否正确
   - 止盈止损是否触发
   - 模拟收益率如何

这套回测系统**能评估“建议文本是否大致说对了”**，但它存在明显局限：

### 1）它回测的是“文本建议”，不是“交易系统本身”
当前选股系统已经进入五层架构：
- L1 市场环境
- L2 题材层
- L3 强势股池
- L4 买点识别
- L5 交易阶段 + 交易计划

但现有回测仍然只看：
- `operation_advice`
- `stop_loss`
- `take_profit`

这意味着：
- 无法知道 L1 是否判断正确
- 无法知道 L2 识别的主线题材是否真的更强
- 无法知道 L3 `leader_pool` 是否优于 `watchlist`
- 无法知道 L4 `setup_type` / `entry_maturity` 是否真的有预测能力
- 无法知道 L5 `trade_stage` 是否真的提升了胜率和收益/回撤比

### 2）它不能反向优化当前五层系统
真正有价值的回测系统，不只是回答：
> 当时建议“买入”对不对？

而应该回答：
- 在 `aggressive/balanced/defensive/stand_aside` 下，哪个 regime 的判断最有效？
- `main_theme / secondary_theme / follower_theme / non_theme` 的分层是否有效？
- `leader_pool / focus_list / watchlist` 的未来表现是否显著分化？
- 哪类 `setup_type` 在什么环境里最好？
- `entry_maturity=HIGH` 是否真的优于 `MEDIUM/LOW`？
- `probe_entry` 与 `add_on_strength` 的胜率和收益曲线是否合理？
- 哪些规则经常导致误判？

### 3）当前回测无法形成“优化闭环”
你现在要的是：

> 用回测系统不断优化和改进当前选股系统，提高选股准确率和买卖点识别准确率。

这要求回测系统不只是输出汇总统计，而要形成：

**候选记录 → 五层决策快照 → 未来结果 → 分组统计 → 偏差定位 → 策略调参建议**

当前系统还做不到这个闭环。

---

## 二、重构目标：把回测系统改造成“交易系统评估器”

新的回测系统不应再只是评估“文本建议对不对”，而应评估：

### 目标 1：评估五层系统各层输出是否有预测能力
按层验证：
- L1 输出是否能过滤掉低胜率市场
- L2 输出是否能识别更强主线题材
- L3 输出是否能挑出未来更强的个股
- L4 输出是否能识别高质量买点
- L5 输出是否能生成更合理的执行级决策

### 目标 2：评估“组合条件”是否有效
不是只看单字段，而是看组合：
- `balanced + main_theme + leader_pool + trend_breakout + HIGH`
- `aggressive + main_theme + add_on_strength`
- `defensive + secondary_theme + probe_entry`

这些组合才是真正的交易系统语言。

### 目标 3：支持规则优化和参数迭代
新的回测系统应能告诉我们：
- 某个阈值是不是太宽了
- 哪个 `setup_type` 在 `defensive` 里其实失效
- 哪种 `theme_position` 与 `entry_maturity` 的组合会造成大量假阳性
- 哪类 `trade_plan` 容易过早止损或过早止盈

### 目标 4：形成闭环迭代能力
最终要形成：

> 五层输出记录 → 回测评估 → 分层统计 → 偏差发现 → 调参/改规则 → 再回测验证

---

## 三、建议的新回测系统定位

建议把回测系统从当前的：

> **Advice Backtest（建议文本回测）**

重构为：

> **Five-Layer Decision Backtest & Calibration System（五层决策回测与校准系统）**

它应包括三个核心子系统：

### A. 事件回放层（Replay Layer）
负责复盘某个历史交易日，重现当时系统会输出什么：
- 市场环境
- 热点题材
- 候选股分池
- 买点类型/成熟度
- 交易阶段
- 交易计划

### B. 结果评估层（Evaluation Layer）
负责看未来表现，评估：
- 方向是否正确
- 入场点是否有效
- 止损是否合理
- 止盈是否合理
- 回撤是否可接受
- 风险收益比如何

### C. 校准分析层（Calibration Layer）
负责统计各类条件的历史表现，输出：
- 哪些规则有效
- 哪些条件应收紧
- 哪些组合应该降权/废弃
- 哪些 setup/阶段在不同 regime 下表现最好

---

## 四、当前系统与目标系统的结构差异

| 维度 | 当前回测系统 | 目标回测系统 |
|---|---|---|
| 回测对象 | `operation_advice` 文本 | 五层决策快照 |
| 核心输入 | 分析记录 + 日线 | 候选结果 + 五层字段 + 交易计划 + 日线/分时 |
| 核心问题 | 建议方向对不对 | 交易系统各层有没有预测力 |
| 输出 | win/loss/neutral, simulated_return | 各层有效性、组合有效性、参数质量、阶段收益分布 |
| 优化能力 | 弱 | 强 |
| 是否可反哺策略系统 | 很有限 | 强闭环 |

---

## 五、建议的重构架构

---

### 模块 1：回测对象重构 —— 从 `AnalysisHistory` 转向 `ScreeningCandidateSnapshot`

### 当前问题
回测入口仍基于 `AnalysisHistory`，这更像“单股分析建议回测”。

### 新目标
新的回测主对象应优先基于：
- `screening_runs`
- `screening_candidates`
- 候选持久化结果中的五层字段

需要完整记录每个候选在被选出当下的：
- `market_regime`
- `theme_position`
- `candidate_pool_level`
- `setup_type`
- `entry_maturity`
- `trade_stage`
- `trade_plan`
- `ai_trade_stage` / AI 审核结果
- 关键 factor snapshot

### 建议动作
1. 将 `screening_candidates` 作为主要回测源
2. 若已有持久化字段不足，补充快照字段
3. 允许按 `run_id` / `trade_date` / `strategy_name` / `trade_stage` 回测

---

### 模块 2：回测粒度重构 —— 从“文本方向正确性”扩展到“五层决策有效性”

建议把回测指标拆成五层：

#### L1 市场环境层指标
- 各 `market_regime` 下的候选平均收益
- 各 `market_regime` 下的胜率
- `stand_aside` 日是否显著降低回撤
- 环境过滤前后收益差异

#### L2 题材层指标
- `main_theme / secondary_theme / follower_theme / non_theme` 的收益分布
- 主线题材候选 vs 非主线题材候选的命中率差异
- 不同题材阶段的后续表现

#### L3 强势股池层指标
- `leader_pool / focus_list / watchlist` 的未来收益、胜率、最大回撤
- pool 层级的排序有效性
- 入池规则是否过宽/过窄

#### L4 买点层指标
- 各 `setup_type` 在不同环境/题材下的收益分布
- `entry_maturity` 的分层有效性
- 假突破、假背离、伪回踩等失败模式识别

#### L5 交易阶段层指标
- `watch/focus/probe_entry/add_on_strength` 的未来表现
- `probe_entry` 是否合理区分“可轻仓试错”与“只值得关注”
- `add_on_strength` 是否真的拥有更高胜率/更高盈亏比

---

### 模块 3：交易计划回测 —— 从静态止盈止损，升级到结构化 plan 验证

当前回测只验证：
- `stop_loss`
- `take_profit`

但新系统已有 `trade_plan`，应回测：
- 初始仓位建议是否过重/过轻
- 加仓规则是否合理
- 止损规则是否过紧/过松
- 止盈计划是否过早兑现利润
- 失效条件是否比简单止损更有效

### 建议新增评估字段
- `plan_entry_validity`
- `plan_stop_loss_quality`
- `plan_take_profit_quality`
- `plan_r_multiple`
- `plan_max_adverse_excursion`（最大不利波动）
- `plan_max_favorable_excursion`（最大有利波动）

### 建议演进阶段
#### Phase 1
先基于日线 OHLC 完成计划质量评估

#### Phase 2
如条件允许，引入分时/分钟级数据，提高买卖点回测真实性

---

### 模块 4：组合分析与归因 —— 让回测可指导调参

新的回测系统必须支持分组统计。

### 必须支持的分组维度
- `market_regime`
- `theme_position`
- `candidate_pool_level`
- `setup_type`
- `entry_maturity`
- `trade_stage`
- `strategy_name`
- `ai_trade_stage`
- 是否命中 `leader_score` 高阈值
- 是否来自 OpenClaw 外部题材主线

### 建议输出的归因问题
- 哪类 regime 下系统容易误选？
- 哪类题材位置的胜率最差？
- 哪种买点在什么环境下最失效？
- 哪类阶段建议太激进？
- 是题材错了，还是买点错了，还是止损太紧？

### 建议新增能力
- 分组 summary 表
- 自动生成“低效组合排行榜”
- 自动生成“高效组合排行榜”
- 自动输出建议的规则收敛方向

---

### 模块 5：回测数据模型重构

建议新增/调整以下数据结构。

#### 1. `backtest_runs`
记录一次回测任务：
- 回测范围
- 时间范围
- 数据版本
- 引擎版本
- 是否使用 strict gate / relaxed gate
- 是否启用 AI 审核结果

#### 2. `backtest_candidate_evaluations`
按“候选股 × 回测运行”记录：
- 基本标识：`run_id`, `candidate_id`, `trade_date`, `code`
- 五层快照：
  - `market_regime`
  - `theme_position`
  - `candidate_pool_level`
  - `setup_type`
  - `entry_maturity`
  - `trade_stage`
  - `trade_plan_json`
- 结果字段：
  - `forward_return_1d/3d/5d/10d`
  - `max_upside_pct`
  - `max_drawdown_pct`
  - `mae_pct`
  - `mfe_pct`
  - `hit_stop_loss`
  - `hit_take_profit`
  - `stage_success`
  - `plan_success`
  - `signal_quality_score`

#### 3. `backtest_group_summaries`
按组聚合：
- scope_type（例如 regime/theme/pool/setup/stage/组合）
- scope_key
- 样本数
- 胜率
- 平均收益
- 最大回撤均值
- 收益分布
- hit ratio

#### 4. `backtest_calibration_recommendations`
记录系统给出的优化建议：
- 建议类型
- 证据指标
- 建议动作
- 影响范围

---

## 六、建议的核心指标体系

为了支持“优化选股系统”，建议至少建立以下指标族：

---

### 1）选股准确率指标
衡量“被选出来的票，未来是否真的更强”

建议指标：
- Top-K 命中率
- 候选池超额收益
- `leader_pool` vs 全市场基准
- `leader_pool` vs `focus_list`
- 选中股未来 3/5/10 日上涨概率

---

### 2）题材识别准确率指标
衡量“主线题材是不是真的主线”

建议指标：
- `main_theme` 候选平均收益
- 主线题材内股票的相对收益
- `main_theme` 与 `non_theme` 的收益差
- 不同 `theme_stage` 的后验表现

---

### 3）买点识别准确率指标
衡量“setup_type / entry_maturity 是否真的预测更好入场点”

建议指标：
- 各 `setup_type` 的未来收益率分布
- `HIGH` vs `MEDIUM` vs `LOW` 胜率对比
- 入场后 1/3/5 日最大回撤
- 入场后 1/3/5 日最大涨幅

---

### 4）阶段建议准确率指标
衡量“trade_stage 的级别是否合理”

建议指标：
- `watch/focus/probe/add_on` 各阶段平均收益
- `add_on_strength` 是否显著优于 `probe_entry`
- `stand_aside` 时出手候选是否明显劣化
- 各阶段的盈亏比

---

### 5）交易计划质量指标
衡量“止损止盈仓位建议是否合理”

建议指标：
- 止损过早率
- 止盈过早率
- 计划收益兑现率
- 平均 R 倍数
- 计划执行后最大不利波动 / 有利波动

---

## 七、建议的优化闭环机制

新的回测系统不应只是“查报表”，而要形成闭环。

建议闭环如下：

### Step 1：每日记录系统快照
在筛选时，保存完整五层快照

### Step 2：定期回测
按周/月对过去候选进行回测

### Step 3：输出分层统计
输出：
- 哪些层有效
- 哪些组合有效
- 哪些组合失效

### Step 4：生成调参建议
例如：
- `non_theme` 的 `probe_entry` 胜率显著低，建议禁止
- `secondary_theme + HIGH + trend_breakout` 表现不错，可上调优先级
- `bottom_divergence_breakout` 在 `defensive` 下胜率偏低，应降权

### Step 5：应用规则调整
改：
- 阈值
- 门控矩阵
- 权重
- 阶段上限
- setup 优先级

### Step 6：再次回测验证
验证新规则是否真的改善，而不是拍脑袋优化

---

## 八、建议实施路线图

---

### Phase 0：兼容保留旧回测系统
保留当前 `operation_advice` 回测作为：
- 旧版建议评估器
- 与新版回测并存一段时间

不要一刀切删掉。

---

### Phase 1：先做“五层候选回测 MVP”

**目标：先让回测对象从 `AnalysisHistory` 切换到 `screening_candidates`。**

#### 需要完成
1. 为候选回测建立新的 service / engine
2. 读取五层字段
3. 计算未来 1/3/5/10 日表现
4. 输出按以下维度的 summary：
   - `market_regime`
   - `theme_position`
   - `candidate_pool_level`
   - `setup_type`
   - `entry_maturity`
   - `trade_stage`

#### MVP 成功标准
- 能明确回答：
  - 哪一层的分层真的有预测力
  - 哪类候选最值得保留

---

### Phase 2：加入交易计划评估

**目标：不只是评估“选得准不准”，还评估“买卖点和风控方案好不好”。**

#### 需要完成
1. 解析 `trade_plan_json`
2. 基于日线先评估：
   - 止损质量
   - 止盈质量
   - 最大不利波动
   - 最大有利波动
3. 输出 `plan_quality_score`

---

### Phase 3：加入组合归因与校准建议

**目标：让系统能直接产出“怎么优化规则”的建议。**

#### 需要完成
1. 分组分析引擎
2. 高效组合/低效组合排行榜
3. 自动输出调参建议
4. 支持不同规则版本回测对比

---

### Phase 4：引入版本化对比与实验系统

**目标：真正支持“改规则 → 回测 → 验证 → 再改”。**

#### 需要完成
1. 规则版本号记录
2. 回测运行版本记录
3. A/B 规则对比
4. Strict Gate / Relaxed Gate 对比实验

---

## 九、建议修改的代码模块

### 现有模块（需保留但降级为旧回测）
- `src/services/backtest_service.py`
- `src/core/backtest_engine.py`
- `api/v1/endpoints/backtest.py`

### 建议新增模块
#### 服务层
- `src/services/five_layer_backtest_service.py`
- `src/services/backtest_calibration_service.py`
- `src/services/backtest_group_analysis_service.py`

#### 引擎层
- `src/core/five_layer_backtest_engine.py`
- `src/core/trade_plan_evaluator.py`
- `src/core/signal_quality_evaluator.py`

#### 仓储层
- `src/repositories/five_layer_backtest_repo.py`

#### API 层
- `api/v1/endpoints/five_layer_backtest.py`
- `api/v1/schemas/five_layer_backtest.py`

#### 测试
- `tests/test_five_layer_backtest_engine.py`
- `tests/test_five_layer_backtest_service.py`
- `tests/test_trade_plan_evaluator.py`
- `tests/test_backtest_calibration_service.py`

---

## 十、建议优先实现的最小闭环

如果你想尽快落地，不建议一上来做全量终极版，而建议先做下面这个最小闭环：

### 最小闭环 v1
1. 以 `screening_candidates` 为回测对象
2. 回测未来 1/3/5/10 日收益
3. 统计：
   - `market_regime`
   - `theme_position`
   - `candidate_pool_level`
   - `setup_type`
   - `entry_maturity`
   - `trade_stage`
4. 输出各组：
   - 样本数
   - 胜率
   - 平均收益
   - 最大涨幅/最大回撤
5. 输出“低效组合 TopN / 高效组合 TopN”

### 这样立刻能得到什么
你可以马上知道：
- 当前 `leader_pool` 是否真的更强
- `add_on_strength` 是否真的值钱
- `HIGH` 成熟度是否真有区分度
- `main_theme` 是否比 `secondary_theme` 更强
- 哪个 `setup_type` 最靠谱

这就是第一轮真正能优化当前选股系统的数据基础。

---

## 十一、一句话重构目标

> 把当前“回测建议文本”的系统，升级成“回测五层决策链、诊断各层有效性、并能反向指导规则收紧与参数优化”的交易系统回测平台。

---

## 十二、结论

如果项目继续沿用当前回测系统，最多只能知道：
- 某条建议文本大概说得对不对

但如果按本方案重构，你就能知道：
- 市场环境判断是否有效
- 题材主线识别是否有效
- 强势股池是否选对了
- 买点识别是否准确
- 交易阶段建议是否合理
- 哪些规则该收紧，哪些 setup 该保留，哪些阈值该调整

这才是真正能推动当前选股系统不断进化的回测系统。

---

*写于 2026-04-08：用于指导 `daily_stock_analysis` 项目将现有回测系统重构为面向五层交易系统的回测、诊断与优化闭环系统。*
