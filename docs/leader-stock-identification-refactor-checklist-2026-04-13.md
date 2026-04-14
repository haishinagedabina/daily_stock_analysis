# 龙头股识别改造清单

**目标：** 在“先识别热点板块，再识别龙头股”的主线下，把当前偏基础强势分的 `leader_score`，改造成真正服务于热点板块内龙头识别的实现。

**适用范围：**
- `Layer 2` 热点板块完成识别之后
- `Layer 3` 候选池分级之前
- `leader_score / leader_pool / leader_candidate_count / front_codes` 相关逻辑

---

## 1. 当前结论

结合现有方案文档、当前代码实现以及最近一次真实运行证据，当前“龙头股识别”存在以下核心偏差：

1. 当前主链路里的 `leader_score` 大多数时候仍是 **基础强势分**，不是“热点板块内龙头分”。
2. 方案要求龙头识别建立在 `theme_match_score` 之上，但当前主链路没有稳定接入题材增强后的 `theme_leader_score`。
3. 书中强调的“涨停速度最快（封板时间最早）”没有真正进入当前主流程的龙头主分。
4. 当前 `leader_pool` 更像“高分强势股池”，不完全等同于“龙头股识别结果”。
5. `SectorHeatEngine` 仍使用 `leader_score >= 70` 统计板块龙头候选，与方案中的 `leader_score >= 50` 有口径偏差。

---

## 2. 对照基准

### 2.1 书中/截图强调的龙头特征

优先级更高的特征：

1. 涨停速度最快（封板时间最早）
2. 流通市值偏小
3. 受益最直接

优先级较低但可辅助判断的特征：

1. 历史地位较高
2. 资金参与度高

### 2.2 当前方案文档中的可实现抽象

当前仓库方案文档已经把龙头识别抽象成五维 `leader_score`：

1. `theme_match_score`
2. 小市值加分
3. 换手率
4. 突破强度
5. 趋势强度

这套抽象本身可以接受，但前提是：

1. 题材匹配必须真正接入主流程
2. 分钟级“涨停速度”至少要作为增强信号进入当前链路
3. `leader_pool` 不能混成单纯“极强股池”

---

## 3. 必须改的项

以下项属于 **必须改**，否则“龙头识别”仍会持续偏离方案原意。

### 3.1 把题材增强后的 leader 分真正接入主流程

**问题：**

当前 `FactorService` 默认计算的是：

- `theme_match_score = 0.0`
- `leader_score_source = "base"`

这意味着当前主流程里的 `leader_score` 主要反映：

- 小市值
- 换手
- 涨停/突破
- 趋势

而不是“热点板块里的龙头程度”。

**改造要求：**

1. 在当前真实选股主链路中接入 `HotThemeFactorEnricher`
2. 当个股属于热点板块/题材时，优先生成并使用 `theme_leader_score`
3. `FiveLayerPipeline`、`SectorHeatEngine`、`CandidatePoolClassifier` 统一优先读取 `theme_leader_score`
4. 仅当题材增强链路缺失时，才回退到 `base_leader_score`

**涉及文件：**

- `src/services/factor_service.py`
- `src/services/hot_theme_factor_enricher.py`
- `src/services/five_layer_pipeline.py`
- `src/services/sector_heat_engine.py`

---

### 3.2 明确区分“龙头识别”和“强势股打分”

**问题：**

当前 `leader_pool` 的准入逻辑里，`extreme_strength_score >= 80` 也可以直接进 `leader_pool`。  
这会让“龙头池”混入“极强但不一定是龙头”的票。

**改造要求：**

1. `leader_pool` 必须优先体现“题材主线 + 龙头性”
2. `extreme_strength_score` 只能做辅助，不应独立替代龙头性
3. 至少要满足以下之一，才能进入 `leader_pool`：
   - `theme_position in (main_theme, secondary_theme)` 且 `leader_score >= threshold`
   - 或者明确命中“题材内前排/龙头”标签
4. 非主线题材票不得靠极强分直接进入 `leader_pool`

**涉及文件：**

- `src/services/candidate_pool_classifier.py`
- `src/services/five_layer_pipeline.py`
- `src/services/theme_position_resolver.py`

---

### 3.3 把“涨停速度最快”从文档概念升级成可落地信号

**问题：**

当前主流程里只有：

- `is_limit_up`
- `gap_breakaway`

而没有真正把：

- 最早封板
- 开盘半小时内涨停
- 分时封板速度

作为有效龙头信号参与当前主线。

**改造要求：**

1. 第一阶段先落一个稳定代理信号：
   - `limit_up_within_30min`
   - 或 `intraday_minutes_since_open <= 30`
2. 该信号至少应进入：
   - `theme_leader_score` 的增强项
   - `entry_reason`
   - `leader candidate` 的解释字段
3. 不要求第一阶段就做“全市场最早封板排名”，但必须比当前“只看是否涨停”更进一步

**涉及文件：**

- `src/services/hot_theme_factor_enricher.py`
- `src/services/leader_stock_selector.py`
- `src/services/leader_score_calculator.py`
- `src/services/factor_service.py`

---

### 3.4 把 `leader_score` 阈值口径统一

**问题：**

当前存在至少三套口径：

1. 方案文档：`leader_score >= 50`
2. `SectorHeatEngine`：`leader_score >= 70`
3. `CandidatePoolClassifier`：`leader_pool >= 70`，`defensive >= 80`

这会导致：

1. 板块质量标签偏严
2. 板块层的 `leader_candidate_count` 经常偏低
3. `leader_pool` 和板块“有无龙头”语义错位

**改造要求：**

1. 先区分两个层级：
   - `leader_candidate_threshold`
   - `leader_pool_threshold`
2. 建议：
   - 板块层“是否存在龙头候选”用较宽阈值，如 `>= 50`
   - 候选池进入 `leader_pool` 用更严格阈值，如 `>= 65/70`
3. `SectorHeatEngine` 不要继续用过严阈值把板块“无龙头化”

**涉及文件：**

- `src/services/sector_heat_engine.py`
- `src/services/candidate_pool_classifier.py`
- `docs/strategy_system_refactor_plan.md`（如需同步文档口径）

---

## 4. 应该改，但可以后置的项

以下项很重要，但可排在“主流程题材增强接通”之后。

### 4.1 引入“受益最直接”的更强代理

当前 `theme_match_score` 只能近似表达“受益最直接”，还不够交易语义化。

建议后续增强：

1. 区分“核心板块命中”与“外围板块命中”
2. 对同一题材下的股票，增加“主板块优先级”概念
3. 允许 `ThemeMappingRegistry` 为不同板块配置：
   - `core_board`
   - `secondary_board`
   - `peripheral_board`

这样“刀片电池主升票”和“沾边消费电子票”不会被同等对待。

### 4.2 引入板块内相对排序

当前 `leader_score` 还是单票绝对打分，缺少“在题材内是否前排”的相对语义。

建议后续增加：

1. `theme_leader_rank`
2. `theme_front_rank`
3. `theme_front_percentile`

使“龙头”不只看绝对分，还要看在本题材内的相对位置。

### 4.3 历史龙头地位与辨识度

书里提到“历史地位较高”，当前系统没有对应实现。

建议后续用非硬门槛方式补充：

1. 近 N 日是否持续位于题材前排
2. 是否多次成为板块领涨/涨停样本
3. 是否在板块内连续高排名

这类特征适合作为加分或解释字段，不建议第一阶段做成硬门槛。

---

## 5. 暂不建议在第一阶段做的项

以下项有价值，但不建议放进第一轮主改造：

1. 全量分时“最早封板排名”全市场回放
2. 复杂资金博弈指标
3. 新闻/研报级别的产业链受益深度理解
4. embedding 级别的题材语义补强

原因：

1. 当前主问题不是“高级特征不够多”，而是“题材增强分根本没接上主流程”
2. 第一阶段应该优先修正主链路语义，再做高级增强

---

## 6. 推荐改造顺序

建议按下面顺序推进：

### Phase 1：接通主流程

1. 让 `HotThemeFactorEnricher` 真正进入主流程
2. 确保热点股可以生成 `theme_leader_score`
3. 确保 `leader_score_source` 在真实运行里不再全部是 `base`

### Phase 2：纠正候选池语义

1. 收紧 `leader_pool` 的“极强股破格进入”路径
2. 让 `leader_pool` 更贴近“题材主线龙头池”
3. 把 `focus_list / watchlist` 与 `leader_pool` 语义重新拉开

### Phase 3：补齐龙头增强项

1. 把“开盘半小时内涨停”纳入龙头增强项
2. 给题材内股票增加相对前排排序
3. 为“受益最直接”补更强代理特征

---

## 7. 最小验收标准

改完后，至少要满足以下验收条件：

1. 真实运行日志里，`leader_score_source_counts` 不再长期是 `{"base": 全量股票数}`
2. 热点板块中的前排股票，能产生非 0 的 `theme_leader_score`
3. `leader_candidate_count` 不再长期大面积为 0
4. `leader_pool` 中的股票，绝大多数都属于 `main_theme / secondary_theme`
5. 同一天热点板块中的龙头票，其解释字段能体现：
   - 题材命中
   - 小市值/活跃换手
   - 涨停/突破
   - 若有分钟级数据，则体现“开盘半小时内涨停”

---

## 8. 建议新增/补强的日志

为了后续继续验证，建议至少补以下统计：

1. `leader_score_source_counts`
2. `theme_leader_score_nonzero_count`
3. `leader_candidate_count_by_board`
4. `leader_pool_count_by_theme_position`
5. `leader_pool_candidate_preview`
6. `limit_up_within_30min_count`

---

## 9. 建议补的测试

建议新增或补强以下测试：

1. `theme_leader_score` 优先于 `base_leader_score`
2. 热点命中后，`leader_score_source` 从 `base` 切换到 `theme`
3. `leader_pool` 不允许 `non_theme` 或 `follower_theme` 破格进入
4. `leader_candidate_threshold` 与 `leader_pool_threshold` 分层生效
5. `limit_up_within_30min` 能提升龙头识别结果或解释字段

---

## 10. 直接结论

如果只用一句话总结当前问题：

**当前代码已经有“龙头打分器”，但还没有把它真正做成“热点板块之后的龙头识别器”。**

第一阶段最重要的事不是继续加更多龙头特征，而是：

1. 把题材增强分接进主流程
2. 让 `leader_pool` 回到“主线龙头池”的语义
3. 把“涨停速度”从注释/辅助信息升级成有效特征
