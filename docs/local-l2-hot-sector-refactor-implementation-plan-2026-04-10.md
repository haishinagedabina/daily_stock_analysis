# L2 本地热点板块重构实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将当前“绝对分数 + 固定阈值”的本地板块热度识别，重构为“市场相对排名驱动”的热点板块识别体系，使 L2 真正符合“先板块后个股”的方案原意。

**Architecture:** 保留 `SectorHeatEngine -> ThemeAggregationService -> ThemePositionResolver -> FiveLayerPipeline` 主链路，但重写 `SectorHeatEngine` 的核心判定语义：把“热点板块识别”与“板块质量过滤/生命周期标签”拆开。`hot/warm` 改为由板块强度排名产生，`leader/persistence/stage` 改为解释和分层信息，而不是先天决定热点是否存在。

**Tech Stack:** Python、pandas、SQLite/SQLAlchemy、pytest、现有 `DailySectorHeat` 持久化表、现有 five-layer pipeline。

---

## 1. 背景与运行证据

本计划不是凭代码直觉生成，而是基于本次调试日志收敛出的结论。

### 已确认的运行事实

1. **L2 参与计算的板块覆盖正常**
   - 调试日志显示：`active_board_count=926`，`computed_sector_count=925`
   - 结论：不是“板块没参与计算”导致热点缺失

2. **没有 hot 的直接原因是原始分数上不去**
   - 调试日志显示：`raw_status_counts={"neutral":719,"cold":202,"warm":4}`
   - 最高原始分仅 `68.47`，低于 `HOT_THRESHOLD=70`
   - 结论：当前运行里不是“hot 被后置降级”，而是“原始分类阶段就没有 hot”

3. **硬过滤不是本轮主因**
   - 调试日志显示：`downgraded_hot_count=0`
   - 结论：当前没有 `hot -> warm` 的批量降级

4. **L2 结果没有在本地 / 融合题材链路中丢失**
   - 调试日志显示：`decision_warm_theme_count=27`、`local_theme_count=27`、`fused_theme_count=25`
   - 结论：后续链路只做了归一化和去重，不是导致“没有热点板块”的根因

5. **龙头分支当前几乎全部落在 base 路径**
   - 调试日志显示：`leader_score_source_counts={"base":5304}`
   - 顶部板块样本均为 `leader_count=0`
   - 结论：`leadership` 维度当前对热点识别的影响失真，且 `leader_score >= 70` 很可能不适合作为板块热点定义的一部分

### 根因判断

当前“热点板块几乎都是 `warm`”的根因，不是单个阈值写错，而是 **L2 建模方式已经偏离方案原意**：

- 方案要的是：**板块强度排名**
- 代码做成了：**绝对综合分 + 固定阈值**

这两者的业务语义不同，导致“市场最强方向”也可能只能被打成 `warm`。

---

## 2. 方案原意与当前实现的关键偏差

### 方案原意

依据 `docs/strategy_system_refactor_plan.md`，L2 本地热点板块至少要体现以下事实：

1. 先从全市场识别“今日最强板块/主线方向”
2. 强弱应主要来自**相对排名**
   - 板块涨幅排名（当日 / 近 3 日 / 近 5 日）
   - 涨停家数 / 强势股家数
   - 资金净流入排名（如可得）
3. 生命周期、龙头、前排结构是后续解释和分层信息
4. L2 是总开关，L3 只在这些板块内选股

### 当前实现

当前 `src/services/sector_heat_engine.py` 的核心语义是：

1. 先算四维绝对分
   - `breadth`
   - `strength`
   - `persistence`
   - `leadership`
2. 再算总分 `sector_hot_score`
3. 用固定阈值切 `hot / warm / neutral / cold`
4. 再对 `hot` 做 `breadth / leader / persistence` 硬降级

### 偏差清单

1. **热点板块识别依赖绝对阈值，而不是市场相对排名**
2. **板块强度与生命周期被混成一个总分**
3. **`leader_score >= 70` 被间接提前绑定到热点定义**
4. **`warm+expand` fallback 正在替代本应存在的真正热点识别**
5. **L2 输出的 `hot/warm` 语义更像“打分档位”，不是“市场热点层级”**

---

## 3. 改造目标

## 3.1 目标状态

重构后，L2 本地热点板块应满足：

1. 即使盘面不是极端高潮，系统也能稳定识别出“今日最强板块”
2. `hot` 表示“今日板块强度处于市场前列”，不是“必须满足一组绝对分阈值”
3. `stage` 表示生命周期，和 `hot/warm` 分开定义
4. `leader / front / persistence` 影响“可交易质量”和“主线优先级”，不决定热点是否存在
5. `ThemePositionResolver` 使用的是“主线/次主线板块集合”，而不是被迫靠 `warm+expand` 兜底

## 3.2 非目标

以下内容不在本轮首批重构范围内：

1. 不重写 OpenClaw 外部题材链路
2. 不修改 L3/L4/L5 的整体架构
3. 不引入 embedding、向量检索等新依赖
4. 不把“资金净流入排名”作为首批上线阻塞项；若当前数据不可得，先预留字段和扩展位

---

## 4. 新的规则设计

## 4.1 将 L2 拆成三类输出

`SectorHeatEngine` 重构后应同时输出三套信息：

1. **板块强度（Board Strength）**
   - 回答：这个板块今天在全市场是不是最强的一批？

2. **板块阶段（Board Stage）**
   - 回答：这个板块处于启动、扩散、高潮还是退潮？

3. **板块质量标签（Board Quality Flags）**
   - 回答：这个板块是否有龙头、前排集中度如何、连续性是否足够？

其中：

- `hot / warm` 只来自 **板块强度排名**
- `stage` 只来自 **时间序列/历史趋势**
- `quality_flags` 用于 **L2 主线优先级和 L3 准入解释**

## 4.2 新的板块强度分应基于排名

建议新增 `board_strength_score`（0-100），由以下“排名型特征”组成：

1. **当日板块涨幅排名**
   - 基于 `avg_pct_chg`
   - 辅助参考 `median_pct`

2. **当日强势股密度排名**
   - `pct_chg > 3%` 占比
   - `pct_chg > 5%` 占比

3. **涨停/强涨停密度排名**
   - `limit_up_count`
   - `limit_up_count / stock_count`

4. **联动广度排名**
   - `up_count / stock_count`

5. **前排强度排名**
   - `top3_avg`
   - 前排涨幅集中度

### 推荐分数公式

首版推荐：

- `day_return_rank_score`: 35%
- `strong_stock_rank_score`: 20%
- `limit_up_rank_score`: 20%
- `breadth_rank_score`: 15%
- `front_rank_score`: 10%

说明：

- 这里所有子项先在**全市场板块集合**里做 rank / percentile，再映射到 0-100
- 禁止再用当前 `-2~6 / 0~10` 这种静态 normalize 直接决定热点板块强度

## 4.3 `hot / warm` 改为 rank bucket，而不是绝对阈值

建议将当前：

- `HOT_THRESHOLD = 70`
- `WARM_THRESHOLD = 62`

替换为“排名分桶”：

### 推荐规则

对当天全部可计算板块按 `board_strength_score` 降序排序：

1. `hot`
   - 取前 `max(3, ceil(active_board_count * 0.02))`
   - 上限建议 `12`
   - 并要求 `board_strength_score >= 60`

2. `warm`
   - 取后续 `max(10, ceil(active_board_count * 0.08))`
   - 上限建议 `40`
   - 并要求 `board_strength_score >= 45`

3. 其余依次归入 `neutral / cold`

### 设计理由

1. 这样可以保证“市场总有相对最强板块”
2. 同时保留一个最低分地板，避免极弱盘面把明显无效板块也抬成 `hot`
3. `hot` 代表“市场前列”，`warm` 代表“值得关注但不一定是主攻方向”

## 4.4 生命周期与热点识别解耦

`persistence` 不应再直接参与 `board_strength_score` 主分。

建议改为：

1. `board_strength_score`
   - 只回答“今天强不强”

2. `board_stage`
   - 由历史板块强度趋势决定
   - 负责输出：`launch / expand / climax / fade`

### 推荐 stage 口径

基于新增的板块历史强度快照：

1. `launch`
   - 当日首次进入 `hot/warm`
   - 或 3 日平均排名显著提升

2. `expand`
   - 连续 2-3 日保持高排名，且当日仍在抬升

3. `climax`
   - 连续高位，且涨停密度/强股密度已接近短期极值

4. `fade`
   - 强度排名明显回落，但仍保留一定市场关注度

## 4.5 龙头/前排从“热点定义”降为“质量标签”

当前 `leader_score >= 70` 不应该决定板块是不是热点。

建议改为：

1. 热点板块照样按排名识别
2. 再给每个热点板块附加质量标签：
   - `has_leader_candidate`
   - `has_limit_up_leader`
   - `front_concentration_high`
   - `persistence_ok`
3. L2 输出时展示这些标签
4. `ThemePositionResolver` 或 L3 再把这些质量标签用于优先级排序

### 结果

- 板块热点识别不再被 `leader_score >= 70` 卡死
- 但“有无龙头”仍能影响后续“是不是主线最优先方向”

---

## 5. 文件结构与职责调整

## 5.1 推荐新增文件

- Create: `src/services/board_strength_ranker.py`
  - 负责把板块原始统计量转换成相对排名分
  - 输出 `board_strength_score / board_strength_rank / percentile`

- Create: `tests/test_board_strength_ranker.py`
  - 独立验证排名分桶、极值、同分处理、最小/最大 bucket 数

## 5.2 推荐修改文件

- Modify: `src/services/sector_heat_engine.py`
  - 从“绝对总分判定器”改为“原始统计 + 排名分层 + 阶段/质量标签”

- Modify: `src/services/theme_position_resolver.py`
  - 从“`hot/warm + stage` 推导主线”改为“板块强度层级 + 阶段 + 质量标签”推导

- Modify: `src/services/five_layer_pipeline.py`
  - 记录新的 L2 统计字段，输出更合理的 `main_theme_board_count / hot_warm_sector_count`

- Modify: `src/services/local_theme_pipeline_service.py`
  - 把新增 `board_strength_score / rank / percentile / quality_flags` 带入本地题材快照

- Modify: `src/storage.py`
  - 为 `DailySectorHeat` 增加必要的持久化字段
  - 建议至少新增：
    - `board_strength_score`
    - `board_strength_rank`
    - `board_strength_percentile`
    - `leader_candidate_count`
    - `quality_flags_json`

## 5.3 推荐测试修改

- Modify: `tests/test_sector_heat_engine.py`
- Modify: `tests/test_five_layer_pipeline.py`
- Modify: `tests/test_local_theme_pipeline_service.py`
- Modify: `tests/test_sector_heat_storage.py`

---

## 6. 实施任务拆解

### Task 1: 冻结当前偏差并补充 RED 测试

**Files:**
- Modify: `tests/test_sector_heat_engine.py`
- Modify: `tests/test_five_layer_pipeline.py`
- Modify: `tests/test_local_theme_pipeline_service.py`

- [ ] **Step 1: 为“排名热点板块”补失败测试**

新增测试场景：

1. 当天存在多个明显强板块，但没有任何板块超过旧 `HOT_THRESHOLD=70`
2. 预期结果应仍然至少识别出一批 `hot`
3. `hot` 的顺序应跟板块强度排名一致，而不是被绝对阈值抹平

- [ ] **Step 2: 为“leader_count=0 但仍可成为热点板块”补失败测试**

新增测试场景：

1. 板块整体强势，涨停和强势股密度高
2. 但个股 `leader_score >= 70` 数量为 0
3. 预期结果：该板块仍可被识别为 `hot`，但 `quality_flags` 标记为 `no_leader_candidate`

- [ ] **Step 3: 为 `ThemePositionResolver` 补失败测试**

新增测试场景：

1. 当天存在 `hot + expand` 板块
2. 这些板块即使没有 `leader_candidate`，也应进入“热点主线候选”
3. `warm+expand` fallback 不应再成为主路径

- [ ] **Step 4: 跑定向测试确认 RED**

Run:

```bash
python -m pytest tests/test_sector_heat_engine.py -v
python -m pytest tests/test_five_layer_pipeline.py -k "theme or l2" -v
python -m pytest tests/test_local_theme_pipeline_service.py -v
```

Expected:

- 现有实现下新增测试失败
- 失败点集中在 `hot/warm` 判定和主线识别上

---

### Task 2: 引入板块强度排名器

**Files:**
- Create: `src/services/board_strength_ranker.py`
- Test: `tests/test_board_strength_ranker.py`

- [ ] **Step 1: 写 `BoardStrengthRanker` 的失败测试**

必须覆盖：

1. 输入多个板块原始统计量，输出稳定排序
2. 同分时使用次级指标打破并列
3. `hot` / `warm` bucket 数量符合动态规则
4. 板块总数很小时仍能输出合理 bucket

- [ ] **Step 2: 实现最小 `BoardStrengthRanker`**

输出结构建议：

```python
{
    "board_strength_score": 83.2,
    "board_strength_rank": 3,
    "board_strength_percentile": 0.97,
    "status_bucket": "hot",
}
```

- [ ] **Step 3: 跑新测试确认通过**

Run:

```bash
python -m pytest tests/test_board_strength_ranker.py -v
```

Expected:

- PASS

---

### Task 3: 重写 `SectorHeatEngine` 的热点识别主流程

**Files:**
- Modify: `src/services/sector_heat_engine.py`
- Test: `tests/test_sector_heat_engine.py`

- [ ] **Step 1: 保留原始统计层，不再用绝对总分直接切 `hot/warm`**

保留：

1. `avg_pct_chg`
2. `up_count / stock_count`
3. `limit_up_count`
4. `front_codes`
5. `leader_codes`
6. `persistence_score`

删除或降权：

1. `persistence` 参与 `sector_hot_score`
2. `leader_score >= 70` 对 `hot` 定义的前置约束

- [ ] **Step 2: 接入 `BoardStrengthRanker`**

对每个板块先计算原始统计量，再统一排名，生成：

1. `board_strength_score`
2. `board_strength_rank`
3. `board_strength_percentile`
4. `sector_status`

- [ ] **Step 3: 将 `sector_stage` 改为历史趋势标签**

要求：

1. `stage` 只回答“启动/扩散/高潮/退潮”
2. `stage` 不再决定是否是热点板块
3. `persistence_score` 改为 `stage` 和 `quality_flags` 的输入

- [ ] **Step 4: 新增 `quality_flags`**

建议至少包含：

1. `has_leader_candidate`
2. `leader_candidate_count`
3. `front_concentration_high`
4. `persistence_ok`
5. `limit_up_cluster`

- [ ] **Step 5: 调整 `reason` 字段输出**

要求：

1. 先写清板块强度排名来源
2. 再写清生命周期
3. 最后写质量标签

避免继续使用现在这种“一个总分 + 若干 append”的不可审计字符串

- [ ] **Step 6: 跑 `SectorHeatEngine` 全部测试**

Run:

```bash
python -m pytest tests/test_sector_heat_engine.py -v
```

Expected:

- 新增排名型测试通过
- 原有基础统计、持久化和边界测试继续通过

---

### Task 4: 调整 `ThemePositionResolver` 的主线判定语义

**Files:**
- Modify: `src/services/theme_position_resolver.py`
- Test: `tests/test_five_layer_pipeline.py`

- [ ] **Step 1: 明确新的主线规则**

建议：

1. `hot + launch/expand` → `main_theme`
2. `hot + climax` → `secondary_theme`
3. `warm + expand` → `secondary_theme / follower_theme`
4. `warm + fade/climax` → `fading_theme`
5. `neutral/cold` → `non_theme`

- [ ] **Step 2: 把 `warm+expand fallback` 从兜底逻辑改为次级规则**

要求：

1. 先使用真正的 `hot` 主线
2. 仅在 `hot` 为空时，允许高排名 `warm` 补位
3. 补位板块数量需小于等于真实 `hot` 逻辑上限

- [ ] **Step 3: 引入质量标签作为主线内排序依据**

同样是 `hot` 时：

1. 有 `has_leader_candidate`
2. 有 `limit_up_cluster`
3. `persistence_ok`

应优先于普通 `hot`

- [ ] **Step 4: 跑集成测试**

Run:

```bash
python -m pytest tests/test_five_layer_pipeline.py -k "theme or l2" -v
```

Expected:

- `main_theme_board_count`
- `identified_theme_position_counts`
- `l2_filter_mode`

与新规则一致

---

### Task 5: 扩展持久化与本地题材快照

**Files:**
- Modify: `src/storage.py`
- Modify: `src/services/local_theme_pipeline_service.py`
- Modify: `tests/test_sector_heat_storage.py`
- Modify: `tests/test_local_theme_pipeline_service.py`

- [ ] **Step 1: 为 `DailySectorHeat` 增加排名字段和质量字段**

建议新增字段：

1. `board_strength_score`
2. `board_strength_rank`
3. `board_strength_percentile`
4. `leader_candidate_count`
5. `quality_flags_json`

- [ ] **Step 2: 持久化新增字段**

要求：

1. `save_sector_heat_batch()` 正确写入
2. `list_sector_heat_history()` 可继续读取旧数据
3. 旧数据缺字段时，读取逻辑要兼容

- [ ] **Step 3: 本地题材管道展示新增字段**

`LocalThemePipelineService` 至少要带出：

1. `board_strength_score`
2. `board_strength_rank`
3. `board_strength_percentile`
4. `quality_flags`

- [ ] **Step 4: 跑存储与本地题材测试**

Run:

```bash
python -m pytest tests/test_sector_heat_storage.py -v
python -m pytest tests/test_local_theme_pipeline_service.py -v
```

Expected:

- 新字段可持久化、可读取、可展示

---

### Task 6: 更新 five-layer 统计、调试日志与回归验证

**Files:**
- Modify: `src/services/five_layer_pipeline.py`
- Modify: `src/services/screening_task_service.py`
- Modify: `docs/screening-five-layer-debug-guide.md`
- Modify: `README.md`
- Modify: `docs/CHANGELOG.md`

- [ ] **Step 1: 更新 L2 统计输出**

要求新增：

1. `hot_sector_count`
2. `warm_sector_count`
3. `top_hot_boards`
4. `top_warm_boards`
5. `board_strength_rank_preview`

- [ ] **Step 2: 保留调试插桩直到修复验证完成**

要求：

1. 修复提交前不要删当前 L2 debug 日志
2. 先做一次 post-fix 复现
3. 确认“hot 识别已恢复为排名驱动”后再移除插桩

- [ ] **Step 3: 运行定向验证**

Run:

```bash
python -m pytest tests/test_sector_heat_engine.py -v
python -m pytest tests/test_five_layer_pipeline.py -k "theme or l2" -v
python -m pytest tests/test_local_theme_pipeline_service.py -v
python -m py_compile src/services/board_strength_ranker.py src/services/sector_heat_engine.py src/services/theme_position_resolver.py src/services/five_layer_pipeline.py src/services/local_theme_pipeline_service.py src/storage.py
```

Expected:

- 相关测试全部通过
- 语法检查通过

- [ ] **Step 4: 做一次真实运行回归**

必须核对：

1. 是否出现稳定的 `hot` 板块
2. `hot` 是否确实来自当日最强板块排名
3. `warm+expand fallback` 是否从主路径退回次路径
4. `local_theme_pipeline` 是否保留排名信息

- [ ] **Step 5: 更新文档**

要求同步：

1. `docs/screening-five-layer-debug-guide.md`
2. `README.md`
3. `docs/CHANGELOG.md`

说明新的：

1. L2 排名型板块识别
2. 热点板块/阶段/质量标签语义
3. 调试与验证方式

---

## 7. 验证标准

重构完成后，至少满足以下标准：

### 运行结果标准

1. 在板块分化明显的交易日，不再出现“最强板块都只有 warm、hot=0”的常态
2. `hot` 板块应与实际盘面最强方向一致，优先反映涨幅排名与强势股密度
3. `stage` 不再主导热点是否存在，而是负责解释热点处于哪个阶段
4. `ThemePositionResolver` 的主线识别不再主要依赖 `warm+expand fallback`

### 测试标准

1. `tests/test_sector_heat_engine.py` 全绿
2. `tests/test_five_layer_pipeline.py` 中 L2/主线相关测试全绿
3. `tests/test_local_theme_pipeline_service.py` 全绿
4. 存储兼容性测试全绿

### 审计标准

运行详情与调试日志应能直接回答：

1. 今天哪些板块是按排名进入 `hot`
2. 这些板块为什么是 `hot`
3. 哪些板块虽然很强，但因质量标签不足被降为次优主线
4. 哪些板块处于启动 / 扩散 / 退潮

---

## 8. 风险与防回归措施

## 8.1 主要风险

1. **bucket 数量过多**
   - 会让 `hot` 板块泛滥，L2 失去门控意义

2. **bucket 数量过少**
   - 会重新回到“热点板块为空”的问题

3. **历史字段兼容性问题**
   - `DailySectorHeat` 增字段后，旧数据读取需兼容

4. **L2 变强后导致 L3 样本骤减**
   - 必须联动观察 `theme_shrink` 后剩余候选数

## 8.2 防回归措施

1. 所有 bucket 规则必须有独立单元测试
2. 必须保留真实运行回归，不允许只看测试绿
3. 修复确认前保留调试日志
4. 若 post-fix 运行仍出现 `hot=0`，不得继续叠加修补；先重新读取日志，再调整排名分桶规则

---

## 9. 回滚方案

如果重构后出现严重回归，按以下顺序回滚：

1. 回滚 `ThemePositionResolver` 新规则，恢复旧主线识别
2. 回滚 `SectorHeatEngine` 的 rank bucket 分类逻辑，保留新增日志
3. 回滚持久化字段写入，但不要删除旧字段读取兼容
4. 用当前调试日志复现，再重新评估 bucket 设计

注意：

- 回滚优先恢复业务可用性
- 不要在未确认 post-fix 成功前删除调试插桩

---

## 10. 实施顺序建议

推荐严格按以下顺序推进：

1. 先补 RED 测试，锁定“排名驱动热点板块”的目标行为
2. 再引入 `BoardStrengthRanker`
3. 再重写 `SectorHeatEngine`
4. 再调整 `ThemePositionResolver`
5. 再扩展持久化和本地题材面板
6. 最后跑真实运行回归并更新文档

不要跳步，不要一口气同时改：

- `SectorHeatEngine`
- `ThemePositionResolver`
- `FiveLayerPipeline`

否则无法判定是“热点识别错了”，还是“主线映射错了”。

---

## 11. 交付物清单

本计划完成后，最终应交付：

1. 排名驱动的 L2 热点板块识别逻辑
2. 可审计的板块强度 / 阶段 / 质量标签
3. 更合理的主线/次主线识别
4. 本地题材管道中的排名型明细
5. 对应测试
6. 调试手册、README、CHANGELOG 同步更新

---

## 12. 执行备注

1. 本计划是“最佳改造路径”，不是最小补丁
2. 首批上线可以暂不接资金净流入排名，但字段与扩展位应预留
3. 除非用户明确要求，否则不要在实施过程中自动提交 git commit
