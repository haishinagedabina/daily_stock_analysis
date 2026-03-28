# OpenClaw 热点题材触发的“极端强势组合”策略设计

## 1. 文档目标

本文档用于替换旧版“缺口 + 涨停 + 热点题材”集成方案。

新版方案不再假设 `daily_stock_analysis`（以下简称 DSA）负责热点新闻搜索，也不再以 `SearchService` 为热点题材发现入口。新的边界定义如下：

- `OpenClaw` 负责收集热点新闻、归纳利好板块/题材，并通过接口把题材上下文传给 DSA
- `DSA` 不负责热点新闻发现，只负责从题材开始的后续流程
- 该能力在 DSA 中落地为一条新的选股策略，而不是一条独立平行流水线
- 除了“触发方式来自 OpenClaw”和“候选池有热点板块硬门槛”以外，其余流程与现有策略保持一致

本方案目标是让“热点题材 + 极端强势技术形态”的组合成为 DSA 的标准策略能力，并能：

- 在选股页中作为一条可执行策略展示
- 在运行结果页中展示命中原因、热点题材上下文和最终评分
- 在历史记录列表中与其他策略结果一起沉淀

---

## 2. 结论先行

### 2.1 正确接法

```text
OpenClaw
    ↓  (POST 热点题材上下文)
OpenClaw 专用筛选接口
    ↓
ThemeContextIngestService
    ↓
ScreeningTaskService
    ↓
FactorService
    ↓
StrategyScreeningEngine
    ↓
extreme_strength_combo.yaml
    ↓
候选结果 / AI 二筛 / 历史记录 / Web 展示
```

### 2.2 核心原则

1. DSA 不在主链路内调用 OpenClaw runtime，也不依赖 OpenClaw 在线可用
2. OpenClaw 只提供“热点题材上下文”，不提供候选股票池
3. 新能力以“策略”形式进入现有筛选体系，而不是旁路新任务类型
4. 热点题材是候选池硬门槛，不是全市场通用加分项
5. 进入候选池后的排序采用“基础分 + 多信号叠加加分”模型
6. 运行结果、前端展示、历史记录均复用现有 screening run 体系

---

## 3. 需求重述

这条策略的业务定义是：

- 由 OpenClaw 在盘前或盘中收集热点新闻，归纳出利好板块/题材
- DSA 接收到这些题材后，只在这些题材相关股票中做后续筛选
- 该策略不是“全满足才入选”的硬条件组合，而是“满足越多越强”的极端强势组合

评分逻辑的核心语义：

- 热点板块命中是准入门槛
- `MA100` 之上是基础分
- 在基础分之上，`低位123`、`跳空涨停`、`突破性缺口`、`底背离双突破`、`量能活跃`、`龙头特征` 等继续叠加加分
- 最终按总分输出候选

也就是说，这条策略的本质不是“一个固定形态”，而是“热点题材约束下的强势信号聚合器”。

---

## 4. 与旧版方案的差异

旧版方案的核心前提是：

- DSA 内部新增热点新闻搜索层
- 在 DSA 内部提炼题材
- 再把题材映射到股票池

新版方案明确废弃这一前提，原因如下：

1. 热点新闻收集能力已经确定由 OpenClaw 承担
2. DSA 继续建设内部热点新闻搜索层会造成能力重叠
3. 本次真正需要建设的能力不是“找热点”，而是“消费外部热点并转化成策略筛选结果”

因此，以下方向不再作为本方案目标：

- 在 DSA 内部新增热点新闻搜索桥接层
- 在 DSA 主链路中直接调用 OpenClaw skill runtime
- 在 DSA 中建设独立的热点新闻提炼流水线

---

## 5. 新策略定位

### 5.1 策略名称

建议新增策略：

- `extreme_strength_combo`
- 展示名：`极端强势组合`

### 5.2 策略定义

该策略用于从 OpenClaw 提供的热点题材中，筛选出具备明显强势特征、且多个技术/情绪信号共振的候选股票。

### 5.3 适用市场

- 第一版仅支持 A 股

### 5.4 与现有策略的关系

该策略不是替代现有策略，而是复用现有因子结果做组合加权：

- `gap_limitup_breakout`
- `ma100_low123_combined`
- `ma100_60min_combined`
- `bottom_divergence_double_breakout`
- 以及已有趋势、量能、换手、流动性相关因子

它的定位更接近“上层聚合策略”。

---

## 6. 系统边界

### 6.1 OpenClaw 负责什么

- 热点新闻收集
- 题材/板块归纳
- 利好原因提炼
- 证据摘要整理
- 调用 DSA 专用接口触发这条策略

### 6.2 DSA 负责什么

- 接收并校验外部题材上下文
- 将题材写入本次 screening run
- 从题材出发映射相关股票池
- 计算个股是否属于热点题材范围
- 计算“极端强势组合”总分
- 输出候选结果、命中原因和操作提示
- 在选股页和历史列表中展示结果

### 6.3 OpenClaw 不负责什么

- 不传候选股票池
- 不参与后续技术信号判断
- 不负责 MA100 / 123 / 缺口 / 涨停 / 底背离的计算
- 不参与 DSA 的排序结果裁决

---

## 7. 对外接口设计

### 7.1 入口定位

新增一个 OpenClaw 专用接口：

- `POST /api/v1/screening/openclaw-theme-run`

该接口本质上是“创建一条使用 `extreme_strength_combo` 策略的 screening run”，而不是单独定义一种新任务体系。

### 7.2 请求体

推荐请求结构：

```json
{
  "trade_date": "2026-03-26",
  "market": "cn",
  "themes": [
    {
      "name": "机器人",
      "heat_score": 90,
      "confidence": 0.85,
      "catalyst_summary": "政策催化 + 产业事件驱动",
      "keywords": ["人形机器人", "丝杠", "减速器"],
      "evidence": [
        {
          "title": "示例新闻标题",
          "source": "36kr",
          "url": "https://example.com/news/1",
          "published_at": "2026-03-26T08:20:00+08:00"
        }
      ]
    }
  ],
  "options": {
    "candidate_limit": 50,
    "ai_top_k": 10,
    "force_refresh": false
  }
}
```

### 7.3 响应体

建议复用现有 screening run 响应风格：

```json
{
  "run_id": "run_xxx",
  "status": "queued",
  "strategy_names": ["extreme_strength_combo"],
  "accepted_theme_count": 1,
  "created_at": "2026-03-26T09:01:23+08:00"
}
```

### 7.4 关键约束

- `strategy_names` 由后端固定注入为 `["extreme_strength_combo"]`
- `market` 第一版固定为 `cn`
- `themes` 不能为空
- 没有热点题材时直接拒绝创建 run

---

## 8. 内部数据结构

### 8.1 ThemePayload

```python
@dataclass
class ExternalTheme:
    name: str
    heat_score: float
    confidence: float
    catalyst_summary: str
    keywords: list[str]
    evidence: list[dict]
```

### 8.2 Run 级上下文

```python
@dataclass
class OpenClawThemeContext:
    source: str
    trade_date: str
    market: str
    themes: list[ExternalTheme]
    accepted_at: str
```

### 8.3 候选级补充字段

建议新增以下字段进入 factor snapshot 或候选结果：

- `primary_theme`
- `theme_tags`
- `theme_heat_score`
- `theme_match_score`
- `is_hot_theme_stock`
- `leader_score`
- `extreme_strength_score`
- `extreme_strength_reasons`
- `entry_mode_hint`
- `theme_catalyst_summary`

---

## 9. DSA 内部执行流程

### 9.1 总流程

```text
1. OpenClaw 调用专用接口
2. DSA 校验并落盘 theme_context
3. 创建 screening run
4. ScreeningTaskService 正常执行
5. FactorService 构建基础因子
6. Theme 过滤层给每只股票打上题材归属和龙头特征
7. extreme_strength_combo 策略按总分排序
8. AI 二筛继续沿用现有 candidate_analysis_service
9. 结果写入候选、详情、历史列表
```

### 9.2 不新增平行主流程

本方案明确不新增独立“theme run engine”，而是在现有 `ScreeningTaskService` 中插入一层主题上下文消费逻辑。

---

## 10. 热点板块硬门槛

### 10.1 门槛定义

只有同时满足以下条件的股票，才进入 `extreme_strength_combo` 的正式评分阶段：

1. 股票至少匹配一个外部热点题材
2. 匹配结果达到最低题材相关度阈值

### 10.2 题材匹配来源

建议综合以下信息：

- `get_belong_boards(stock_code)` 返回的所属板块
- 股票名称与题材名/关键词匹配
- 可选的概念板块别名表

### 10.3 匹配评分建议

```text
board_match_score   0.0 ~ 1.0
name_match_score    0.0 ~ 1.0
keyword_match_score 0.0 ~ 1.0

theme_match_score =
    board_match_score * 0.55 +
    name_match_score * 0.20 +
    keyword_match_score * 0.25
```

建议阈值：

- `theme_match_score >= 0.60` 才认定为热点板块命中

---

## 11. 龙头股筛选（定性层）

热点命中的股票进入候选池后，需要再计算龙头特征分。

### 11.1 第一版可稳定实现的龙头特征

- 流通市值偏小
- 换手率较高
- 趋势状态较好
- 涨停/突破特征明显
- 板块匹配度高

### 11.2 高风险但有价值的特征

以下特征在第一版可以先作为可选增强项，不建议做硬门槛：

- 当日最早封板
- 开盘半小时内涨停
- 分时封板速度

原因是这些信息依赖分钟级或分时数据，不是当前 screening 主链路里的稳定基础字段。

### 11.3 leader_score 建议

```text
theme_match_score      35
small_circ_mv_score    20
turnover_score         20
breakout_strength      15
trend_strength         10
--------------------------
leader_score          100
```

---

## 12. 极端强势组合评分模型

### 12.1 策略形态

这条策略不是“必须全部满足”，而是：

- 热点题材命中为硬门槛
- 主信号给基础分
- 其他强势信号累积加分
- 最终按总分排序

### 12.2 推荐总分结构

```text
extreme_strength_score =
    base_score
  + theme_score
  + leader_bonus
  + signal_bonus
  + execution_bonus
```

### 12.3 基础分

`MA100` 是基础分中心：

```text
above_ma100 = True                   -> +20
ma100_breakout_days in 1~5           -> +10
pullback_ma100 / pullback_ma20       -> +5
```

### 12.4 主要叠加信号

```text
pattern_123_low_trendline            -> +12
ma100_low123_confirmed               -> +10
gap_breakaway                        -> +15
is_limit_up                          -> +10
limit_up_breakout                    -> +12
bottom_divergence_double_breakout    -> +12
ma100_60min_confirmed                -> +6
trendline_breakout                   -> +6
```

### 12.5 辅助加分

```text
theme_heat_score high                -> +0~10
leader_score                         -> +0~15
volume_ratio strong                  -> +0~8
turnover_rate active                 -> +0~6
low circ_mv                          -> +0~6
breakout_ratio strong                -> +0~8
```

### 12.6 入选建议

建议策略最终设置两个层次：

- `selected`: 总分高于正式阈值
- `watchlist`: 命中热点题材，但总分略低，可观察

例如：

- `extreme_strength_score >= 70` → 正式入选
- `60 <= score < 70` → 观察名单

---

## 13. 因子复用与新增

### 13.1 可直接复用的现有因子

来自 [factor_service.py](/e:/daily_stock_analysis/src/services/factor_service.py) 的能力：

- `above_ma100`
- `ma100_breakout_days`
- `pullback_ma100`
- `pullback_ma20`
- `gap_breakaway`
- `is_limit_up`
- `limit_up_breakout`
- `pattern_123_low_trendline`
- `ma100_low123_confirmed`
- `ma100_60min_confirmed`
- `bottom_divergence_double_breakout`
- `trendline_breakout`
- `volume_ratio`
- `turnover_rate`
- `breakout_ratio`
- `liquidity_score`
- `trend_score`

### 13.2 需要新增的字段

新增字段应集中在“题材上下文”和“策略聚合分”两类：

- `primary_theme`
- `theme_tags`
- `theme_heat_score`
- `theme_match_score`
- `is_hot_theme_stock`
- `leader_score`
- `extreme_strength_score`
- `extreme_strength_reasons`
- `theme_catalyst_summary`
- `entry_mode_hint`

---

## 14. 策略 YAML 设计

建议新增：

- `strategies/extreme_strength_combo.yaml`

该策略不是自己定义全部底层信号，而是消费 snapshot 中的聚合字段。

示意：

```yaml
name: extreme_strength_combo
display_name: 极端强势组合
description: 热点板块硬门槛下的强势信号聚合策略，综合 MA100、低位123、跳空涨停、底背离等信号进行评分排序。
category: momentum
core_rules: [1, 2, 4, 7]

screening:
  filters:
    - field: is_hot_theme_stock
      op: "=="
      value: true
    - any:
        - field: above_ma100
          op: "=="
          value: true
        - field: pattern_123_low_trendline
          op: "=="
          value: true
        - field: gap_breakaway
          op: "=="
          value: true
        - field: is_limit_up
          op: "=="
          value: true
  scoring:
    - field: extreme_strength_score
      weight: 100
    - field: leader_score
      weight: 20
    - field: theme_heat_score
      weight: 10
```

---

## 15. ScreeningTaskService 接入方式

### 15.1 保持现有运行模型

这条策略的 run 不应是新任务类型，而应继续是标准 screening run。

### 15.2 运行时注入

专用接口在创建 run 时：

- 固定 `strategy_names=["extreme_strength_combo"]`
- 将 `theme_context` 注入本次 run 的上下文

`ScreeningTaskService` 执行时：

- 正常解析股票池
- 正常同步行情
- 正常构建 factor snapshot
- 额外在 factorizing 阶段合并题材字段

### 15.3 AI 二筛

`candidate_analysis_service.py` 保持现有能力：

- 仍然可以对 top K 做个股新闻搜索和 AI 分析
- 但这里的新闻只是候选个股验证，不承担热点发现职责

---

## 16. 前端展示要求

### 16.1 选股页

新策略必须在选股页策略列表中可见，和其他策略同级。

展示要求：

- 策略名：`极端强势组合`
- 可从正常策略列表中选择
- 由 OpenClaw 触发时，前端也能识别该 run 的策略名并正确展示

### 16.2 运行结果页

每个候选应至少展示：

- 最终总分 `extreme_strength_score`
- 主题材 `primary_theme`
- 题材热度 `theme_heat_score`
- 龙头特征分 `leader_score`
- 主要命中原因 `extreme_strength_reasons`
- 关键信号命中情况（MA100 / 123 / 跳空 / 涨停 / 底背离）

### 16.3 历史记录列表

该策略运行结果必须与其他策略一样出现在历史记录中，不新增独立入口。

历史列表至少应支持：

- 展示本次 run 的策略名
- 识别其为 `extreme_strength_combo`
- 能进入详情查看候选及命中原因

---

## 17. 存储设计

### 17.1 题材上下文存储

建议将外部题材上下文与 screening run 绑定，便于结果页和历史页回放。

可选方式：

1. 轻量方案：写入 `config_snapshot`
2. 清晰方案：新增独立表，如 `screening_theme_context`

推荐方式：

- 第一版先写入 `config_snapshot.theme_context`
- 若后续体积或查询复杂度上升，再拆独立表

### 17.2 候选结果存储

候选表或结果 JSON 中应补充：

- `primary_theme`
- `theme_tags`
- `theme_heat_score`
- `leader_score`
- `extreme_strength_score`
- `extreme_strength_reasons`

这样历史记录页和详情页才能无损回放。

---

## 18. 风险与边界

### 18.1 当前高风险点

1. 题材名和板块名不总是一一对应
2. “最早封板/封板速度”依赖分钟级数据，第一版不宜做硬门槛
3. OpenClaw 传入题材质量会直接影响策略结果

### 18.2 第一版建议收敛

第一版应聚焦：

- 热点题材硬门槛
- 题材匹配
- 龙头特征基础分
- 极端强势组合总分
- 标准 run 展示与历史回放

以下内容可以后续增强：

- 分时封板速度
- 开盘半小时涨停识别
- 60 分钟线真实分时验证
- 热点题材别名库自动维护

---

## 19. 分阶段实施建议

### Phase 1

- 新增 OpenClaw 专用接口
- 新增 `extreme_strength_combo` 策略
- 支持题材硬门槛
- 补充聚合分数字段
- 候选结果页展示总分和命中原因

### Phase 2

- 历史记录页展示题材上下文
- AI 二筛 prompt 读取题材上下文
- 优化题材映射和龙头评分

### Phase 3

- 接入分钟级/60 分钟级增强信号
- 支持更精细的封板速度与回踩入场识别

---

## 20. 最终方案摘要

本方案的最终结论是：

- 这项能力在 DSA 中应被实现为一条新的策略：`extreme_strength_combo`
- 触发入口由 OpenClaw 调用专用接口完成
- OpenClaw 只提供“热点题材上下文”，不提供候选股票
- 热点题材命中是硬门槛
- 门槛内股票按“基础分 + 多技术信号叠加加分”排序
- 运行方式、候选结果、前端展示、历史记录都与其他策略保持一致

这意味着我们新增的是：

- 一个新的策略入口
- 一套题材上下文注入能力
- 一套聚合评分模型

而不是一条脱离现有筛选体系的独立流程。
