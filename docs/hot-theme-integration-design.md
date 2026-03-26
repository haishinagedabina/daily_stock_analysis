# “缺口 + 涨停 + 热点题材”代码级集成设计文档

## 1. 文档目标

本文档给出一份**可以直接进入开发实施**的代码级集成方案，用于把《短线操盘实战技法》中的“**缺口 + 涨停 + 热点题材**”策略接入 `daily_stock_analysis` 项目。

这份文档重点解决上一个方案里的核心缺口：

> **如何复用项目当前已经存在的新闻搜索能力，而不是凭空设计一套脱离现有代码的新新闻系统。**

因此，本方案明确规定：

- **DSA 项目内核必须以 `src/search_service.py` 为新闻搜索底座**
- 新增的热点新闻/题材能力必须建立在现有 `SearchService` 之上
- OpenClaw 侧的 news skill / web skill 只作为外部增强或离线旁路，不作为 DSA 主运行时依赖

---

## 2. 结论先行：正确接法

### 2.1 DSA 项目正式接入路径

```text
ScreeningTaskService
    ↓
ThemeContextService                    ← 新增，题材上下文统一入口
    ↓
HotspotSearchService                   ← 新增，热点搜索桥接层
    ↓
SearchService (src/search_service.py)  ← 现有统一搜索底座
    ↓
Tavily / Brave / Bocha / SearXNG / SerpAPI 等 provider
```

### 2.2 关键原则

1. **不直接在 DSA 代码里调用 OpenClaw skill runtime**
2. **不绕开 `SearchService` 自己造第二套 provider 层**
3. **热点新闻能力是 `SearchService` 的上层封装，而不是替代品**
4. **候选股个股新闻分析继续复用现有 `search_stock_news(...)` 逻辑**
5. **最终形成“双层新闻结构”**：
   - 第一层：全局热点新闻 → 提炼题材 → 映射股票池
   - 第二层：候选个股新闻 → AI 二筛 → 验证题材催化与事件细节

---

## 3. 现有新闻能力盘点

## 3.1 项目内已有能力（必须复用）

文件：`src/search_service.py`

已知能力：

- 多 provider 统一抽象
- API key 轮询与故障切换
- 网络重试
- `SearchResponse` / `SearchResult` 统一结构
- 正文抓取 `fetch_url_content(...)`
- 已被 `candidate_analysis_service.py` / pipeline / agent tools 使用

现有已可直接复用的方法语义：

- `search_stock_news(stock_code, stock_name, ...)`
- `search_comprehensive_intel(stock_code, stock_name, ...)`

问题不在于“有没有新闻能力”，而在于：

> **当前新闻能力偏个股维度，尚未封装成“全网热点搜索 / 热点题材搜索”的能力。**

这正是本次集成需要补的一层。

---

## 3.2 OpenClaw / Skill 侧已有能力（只能作为旁路增强）

在 OpenClaw 环境中已确认可用的新闻相关 skill / tool：

- `news-summary`
- `web-search`
- `summarize`
- 原生 `web_search`
- 原生 `web_fetch`

这些能力适合用于：

1. 开发阶段验证 query 方案
2. 生成外部日报 / 旁路缓存文件
3. 失败时人工补录/辅助校验

**但不应成为 DSA 项目内部的主依赖**，因为：

- DSA 是独立 Python 项目
- DSA 的定时任务、测试、部署不能依赖 OpenClaw runtime
- skill 不等价于 DSA 内部可稳定 import 的模块接口

因此本文设计中：

- DSA 主链路 → 只依赖 `src/search_service.py`
- OpenClaw skill → 作为可选旁路输入

---

## 4. 最终目标能力

本次集成后，系统应支持：

1. 使用**现有 SearchService** 搜索：
   - 百度热搜 / 微博热搜 / 知乎热榜 / 36氪 / 华尔街见闻 / 财联社等热点内容
2. 聚合为“每日热点新闻上下文”
3. 用 AI 提炼“可交易题材”
4. 将题材映射到股票池
5. 在 `factor_service.py` 中生成题材因子
6. 在 `strategies/gap_limitup_hot_theme.yaml` 中消费这些因子
7. 在 `candidate_analysis_service.py` 中继续用现有个股新闻搜索，对 top K 进行题材验证

---

## 5. 新旧模块关系

## 5.1 现有模块（保留）

- `src/search_service.py`
- `src/services/factor_service.py`
- `src/services/screener_service.py`
- `src/services/screening_task_service.py`
- `src/services/candidate_analysis_service.py`
- `src/services/analysis_service.py`

## 5.2 新增模块（建议）

- `src/services/hotspot_search_service.py`
- `src/services/theme_extraction_service.py`
- `src/services/theme_mapping_service.py`
- `src/services/theme_context_service.py`

其中：

- `hotspot_search_service.py`：**复用 SearchService 做热点新闻桥接搜索**
- `theme_extraction_service.py`：用 AI 从热点搜索结果提炼题材
- `theme_mapping_service.py`：把题材映射到股票池
- `theme_context_service.py`：统一协调缓存与对外提供题材上下文

---

## 6. SearchService 的代码级扩展设计

本节是本方案的核心。

### 6.1 设计原则

当前 `SearchService` 不应被推翻重写，而应：

- 保留现有 provider 架构
- 保留现有 `SearchResult` / `SearchResponse`
- 新增“热点搜索”与“题材搜索”的高层方法

### 6.2 推荐新增方法

文件：`src/search_service.py`

---

### 方法 1：`search_topic_news(...)`

#### 作用
为“非个股主题搜索”提供统一入口。

#### 方法签名

```python
def search_topic_news(
    self,
    query: str,
    max_results: int = 10,
    days: int = 3,
    preferred_sources: Optional[list[str]] = None,
) -> SearchResponse:
    ...
```

#### 用途示例

- `"AI算力 A股 板块 最新"`
- `"低空经济 概念股 龙头"`
- `"机器人 产业链 财联社 36氪"`
- `"site:top.baidu.com 百度热搜 今日"`

#### 实现建议
内部不需要新建 provider，只需复用现有 provider 选择逻辑与统一 search 流程。

#### 要点
- `preferred_sources` 作为软偏好，不要求 provider 强制支持 source filter
- 返回统一 `SearchResponse`
- 若现有 provider 不支持 source 过滤，则仅用于 query 拼接提示

---

### 方法 2：`search_hotspot_feed(...)`

#### 作用
对“热点平台入口”做专门搜索封装。

#### 方法签名

```python
def search_hotspot_feed(
    self,
    platform: str,
    max_results: int = 10,
    days: int = 1,
) -> SearchResponse:
    ...
```

#### 输入示例
- `platform="baidu"`
- `platform="weibo"`
- `platform="zhihu"`
- `platform="36kr"`
- `platform="wallstreetcn"`
- `platform="cls"`

#### 内部 query 模板建议

```python
HOTSPOT_PLATFORM_QUERIES = {
    "baidu": [
        "site:top.baidu.com 百度热搜 今日",
        "百度热搜 今日 热点",
    ],
    "weibo": [
        "site:s.weibo.com 微博热搜 今日",
        "微博热搜 今日",
    ],
    "zhihu": [
        "site:zhihu.com 知乎热榜 今日",
        "知乎热榜 今日 热门话题",
    ],
    "36kr": [
        "site:36kr.com 36氪 最新资讯",
        "36氪 今日 热门",
    ],
    "wallstreetcn": [
        "site:wallstreetcn.com 华尔街见闻 最新",
        "华尔街见闻 今日 财经热点",
    ],
    "cls": [
        "site:cls.cn 财联社 最新",
        "财联社 今日 热点",
    ],
    "bbc": [
        "site:bbc.com/news BBC 最新新闻",
        "BBC world business technology latest",
    ],
}
```

#### 实现建议
- 针对一个 platform 可依次尝试多条 query
- 将多条 query 结果合并去重
- 返回单个 `SearchResponse` 或内部自定义 `HotspotPlatformSearchResult`

#### 去重标准
建议用：
- 标题规范化 + URL 域名 + snippet 哈希

---

### 方法 3：`search_theme_market_news(...)`

#### 作用
对 AI 已提炼出的题材，做二次市场新闻补强。

#### 方法签名

```python
def search_theme_market_news(
    self,
    theme_name: str,
    max_results: int = 10,
    days: int = 3,
) -> SearchResponse:
    ...
```

#### query 组合建议

```python
queries = [
    f"{theme_name} A股 板块 最新消息",
    f"{theme_name} 概念股 龙头",
    f"{theme_name} 财联社 36氪 华尔街见闻",
]
```

#### 用途
- 为题材提炼结果补充代表性新闻
- 为题材映射服务提供更多板块/个股关键词

---

### 方法 4：`search_multi_queries(...)`

#### 作用
减少上层热点服务反复调用 search 的样板代码。

#### 方法签名

```python
def search_multi_queries(
    self,
    queries: list[str],
    max_results: int = 10,
    days: int = 3,
) -> list[SearchResponse]:
    ...
```

#### 说明
- 顺序执行即可，第一版无需引入并发
- 便于热点服务批量调 query

---

### 6.3 可选新增方法

### `fetch_search_results_content(...)`

#### 作用
对热点搜索结果做正文摘要补全。

#### 签名

```python
def fetch_search_results_content(
    self,
    results: list[SearchResult],
    max_chars: int = 1500,
) -> list[dict]:
    ...
```

#### 说明
内部复用已有 `fetch_url_content(...)`。

该方法可选，不要求第一版实现，但如果要让 AI 提炼题材更稳，会非常有价值。

---

## 7. 新增 HotspotSearchService：桥接现有搜索能力

文件：`src/services/hotspot_search_service.py`

这层的作用非常明确：

> **把现有 SearchService 的“通用搜索能力”转成“每日热点新闻采集能力”。**

### 7.1 不做什么

这个服务不负责：
- 自己维护 provider
- 自己直接抓站
- 自己处理 API key
- 自己做复杂重试

这些都交给 `SearchService`。

### 7.2 负责什么

它负责：
- 维护热点平台 query 模板
- 调用 `SearchService` 搜索
- 归并结果
- 去重清洗
- 标准化平台名称 / 类别 / 热度分数
- 输出给上层 `ThemeExtractionService`

---

### 7.3 数据结构

```python
from dataclasses import dataclass, field
from typing import Optional

@dataclass
class HotspotNewsItem:
    source_platform: str
    source_domain: str
    title: str
    snippet: str
    url: Optional[str]
    published_date: Optional[str] = None
    category: Optional[str] = None
    rank: Optional[int] = None
    search_query: Optional[str] = None
    content_excerpt: str = ""
    heat_score: float = 0.0
```

```python
@dataclass
class HotspotNewsBundle:
    trade_date: str
    generated_at: str
    items: list[HotspotNewsItem]
    warnings: list[str] = field(default_factory=list)
    stats: dict = field(default_factory=dict)
```

---

### 7.4 类设计

```python
class HotspotSearchService:
    def __init__(self, search_service=None, config=None):
        self.search_service = search_service or get_search_service()
        self.config = config or get_config()

    def collect_daily_hotspots(
        self,
        trade_date: date,
        max_items_per_platform: int = 10,
        include_content_excerpt: bool = False,
    ) -> HotspotNewsBundle:
        ...

    def search_platform_hotspot(
        self,
        platform: str,
        max_results: int = 10,
        days: int = 1,
    ) -> list[SearchResult]:
        ...

    def normalize_results(
        self,
        platform: str,
        results: list[SearchResult],
        query: str,
    ) -> list[HotspotNewsItem]:
        ...

    def deduplicate_items(
        self,
        items: list[HotspotNewsItem],
    ) -> list[HotspotNewsItem]:
        ...
```

---

### 7.5 平台配置建议

```python
CORE_HOTSPOT_PLATFORMS = [
    "baidu",
    "weibo",
    "zhihu",
    "36kr",
    "wallstreetcn",
    "bbc",
]

OPTIONAL_HOTSPOT_PLATFORMS = [
    "cls",
    "thepaper",
    "jiemian",
    "yicai",
    "people",
    "cctv",
    "huxiu",
]
```

### 7.6 `collect_daily_hotspots(...)` 伪代码

```python
def collect_daily_hotspots(...):
    items = []
    warnings = []
    stats = {}

    platforms = core + optional
    for platform in platforms:
        try:
            results = self.search_platform_hotspot(platform, ...)
            normalized = self.normalize_results(platform, results, query_used)
            items.extend(normalized)
            stats[platform] = {"count": len(normalized), "ok": True}
        except Exception as exc:
            warnings.append(f"{platform} hotspot search failed: {exc}")
            stats[platform] = {"count": 0, "ok": False, "error": str(exc)}
            continue

    items = self.deduplicate_items(items)

    if include_content_excerpt:
        # optional: fetch_url_content for top-N
        ...

    return HotspotNewsBundle(...)
```

---

## 8. ThemeExtractionService：基于搜索结果提炼题材

文件：`src/services/theme_extraction_service.py`

### 8.1 输入边界

该服务的输入只能来自：
- `HotspotSearchService.collect_daily_hotspots(...)`

不能直接去抓站。

### 8.2 输出结构

```python
@dataclass
class HotTheme:
    theme_name: str
    aliases: list[str]
    heat_score: float
    confidence: float
    event_type: str
    reason: str
    keywords: list[str]
    related_people: list[str]
    source_count: int
    representative_titles: list[str]
```

```python
@dataclass
class ThemeExtractionResult:
    trade_date: str
    generated_at: str
    themes: list[HotTheme]
    warnings: list[str] = field(default_factory=list)
```

### 8.3 类设计

```python
class ThemeExtractionService:
    def __init__(self, llm_adapter=None, config=None):
        ...

    def extract_themes(
        self,
        hotspot_bundle: HotspotNewsBundle,
        top_n: int = 5,
    ) -> ThemeExtractionResult:
        ...
```

### 8.4 Prompt 原则

Prompt 中必须明确：
- 从热点新闻中提炼“可交易题材”
- 输出 JSON
- 禁止输出 crypto 题材
- 必须输出关键词、驱动原因、热度、source_count

### 8.5 与 SearchService 的关系

这里**不再直接用 SearchService**，而是消费已经聚合好的热点新闻包。

如果题材需要二次补强，可通过调用：
- `SearchService.search_theme_market_news(...)`

---

## 9. ThemeMappingService：把题材映射到股票池

文件：`src/services/theme_mapping_service.py`

### 9.1 目标

给股票池中的股票补充题材因子：

- `primary_theme`
- `theme_heat_score`
- `theme_match_score`
- `is_hot_theme_stock`

### 9.2 输入

- `ThemeExtractionResult`
- `universe_df`
- 可选：`fetcher_manager.get_belong_boards(...)`
- 可选：已有个股新闻 / 搜索结果

### 9.3 数据结构

```python
@dataclass
class StockThemeMatch:
    code: str
    name: str
    primary_theme: str | None
    theme_tags: list[str]
    theme_heat_score: float
    theme_match_score: float
    is_hot_theme_stock: bool
    match_reasons: list[str]
    related_hot_people: list[str]
    theme_event_types: list[str]
```

### 9.4 类设计

```python
class ThemeMappingService:
    def __init__(self, fetcher_manager=None, search_service=None, config=None):
        self.fetcher_manager = fetcher_manager
        self.search_service = search_service or get_search_service()
        self.config = config or get_config()

    def map_themes_to_universe(
        self,
        universe_df: pd.DataFrame,
        theme_result: ThemeExtractionResult,
    ) -> dict[str, StockThemeMatch]:
        ...
```

### 9.5 匹配逻辑分层

#### 第一层：板块匹配
使用 `belong_boards` 名称与题材关键词匹配。

#### 第二层：股票名称匹配
使用股票名称与题材别名、关键词匹配。

#### 第三层：可选个股新闻补强
对 top 候选或高分候选可调用：
- `search_service.search_stock_news(stock_code, stock_name, max_results=3)`

注意：
- 这一步不应对全市场全部股票做，否则会过重
- 只对初筛高匹配股票或 top N 做补强

### 9.6 匹配评分建议

```text
board_match_score   0.0 ~ 1.0
name_match_score    0.0 ~ 1.0
news_match_score    0.0 ~ 1.0

final theme_match_score =
    board_match_score * 0.6 +
    name_match_score  * 0.25 +
    news_match_score  * 0.15
```

### 9.7 输出阈值建议

```text
is_hot_theme_stock = (
    theme_heat_score >= 70
    and theme_match_score >= 0.6
)
```

---

## 10. ThemeContextService：统一题材上下文入口

文件：`src/services/theme_context_service.py`

### 10.1 目标

统一管理：
- 每日热点新闻搜索结果
- 每日题材提炼结果
- 股票池题材映射结果
- 缓存读取/落盘

### 10.2 类设计

```python
@dataclass
class ThemeContext:
    trade_date: str
    hotspot_bundle: HotspotNewsBundle
    theme_result: ThemeExtractionResult
    stock_matches: dict[str, StockThemeMatch]
    warnings: list[str] = field(default_factory=list)
```

```python
class ThemeContextService:
    def __init__(
        self,
        hotspot_search_service=None,
        theme_extraction_service=None,
        theme_mapping_service=None,
        config=None,
    ):
        ...

    def get_theme_context(
        self,
        trade_date: date,
        universe_df: pd.DataFrame,
        force_refresh: bool = False,
    ) -> ThemeContext:
        ...
```

### 10.3 内部流程

```python
1. 读取缓存
2. 若无缓存/强制刷新：
   2.1 collect_daily_hotspots(...)
   2.2 extract_themes(...)
   2.3 map_themes_to_universe(...)
   2.4 保存缓存
3. 返回 ThemeContext
```

### 10.4 缓存目录建议

```text
data/theme_context/
  hotspot_news_YYYY-MM-DD.json
  themes_YYYY-MM-DD.json
  theme_matches_YYYY-MM-DD.json
```

---

## 11. ScreeningTaskService 的调用改造

文件：`src/services/screening_task_service.py`

### 11.1 目标

在现有筛选主流程中插入题材上下文准备步骤。

### 11.2 推荐接入点

当前链路大致为：
- universe resolved
- market data synced
- factorizing
- screening
- ai_enriching

建议在 `factorizing` 开始前插入：

```python
theme_context = None
if getattr(self.config, "hot_theme_enabled", False):
    try:
        theme_context = self.theme_context_service.get_theme_context(
            trade_date=effective_trade_date,
            universe_df=universe_df,
            force_refresh=getattr(self.config, "hot_theme_force_refresh", False),
        )
    except Exception as exc:
        logger.warning("theme_context prepare failed: %s", exc)
        if not getattr(self.config, "hot_theme_fail_open", True):
            raise
```

然后在 `build_factor_snapshot(...)` 时传入：

```python
snapshot_df = runtime_factor_service.build_factor_snapshot(
    universe_df=universe_df,
    trade_date=effective_trade_date,
    theme_context=theme_context,
    persist=...,
)
```

### 11.3 构造依赖

建议在 `ScreeningTaskService.__init__` 中新增：

```python
self.theme_context_service = theme_context_service or ThemeContextService(
    hotspot_search_service=HotspotSearchService(),
    theme_extraction_service=ThemeExtractionService(),
    theme_mapping_service=ThemeMappingService(
        fetcher_manager=self.market_data_sync_service.fetcher_manager,
    ),
)
```

### 11.4 第一版是否新增任务阶段？

第一版建议不新增状态阶段，只记录 warning 与日志。

稳定后可增加：
- `hotspot_collecting`
- `theme_extracting`

---

## 12. FactorService 的改造

文件：`src/services/factor_service.py`

### 12.1 目标

将题材上下文真正变成因子，注入 snapshot。

### 12.2 方法签名改造

从：

```python
def build_factor_snapshot(self, universe_df, trade_date, persist=True):
```

改为：

```python
def build_factor_snapshot(
    self,
    universe_df,
    trade_date,
    theme_context=None,
    persist=True,
):
```

### 12.3 新增字段

建议加入 snapshot DataFrame 的字段：

#### 基础字段
- `primary_theme`
- `theme_tags`
- `theme_heat_score`
- `theme_match_score`
- `is_hot_theme_stock`

#### 增强字段
- `theme_match_reasons`
- `related_hot_people`
- `theme_event_types`
- `theme_boost_score`
- `hot_momentum_triggered`

### 12.4 数据填充伪代码

```python
match = theme_context.stock_matches.get(code) if theme_context else None
row["primary_theme"] = match.primary_theme if match else None
row["theme_tags"] = match.theme_tags if match else []
row["theme_heat_score"] = match.theme_heat_score if match else 0.0
row["theme_match_score"] = match.theme_match_score if match else 0.0
row["is_hot_theme_stock"] = match.is_hot_theme_stock if match else False
row["theme_match_reasons"] = match.match_reasons if match else []
row["related_hot_people"] = match.related_hot_people if match else []
row["theme_event_types"] = match.theme_event_types if match else []
row["theme_boost_score"] = (
    (row["theme_heat_score"] / 100.0) * 0.5 + row["theme_match_score"] * 0.5
)
row["hot_momentum_triggered"] = bool(
    row.get("gap_breakaway", False) or row.get("limit_up_breakout", False)
)
```

### 12.5 注意事项

- DataFrame 中 list 字段要注意后续存储兼容性
- 如已有 snapshot 落库逻辑不支持复杂类型，第一版可先序列化为 JSON string

---

## 13. 新增策略 YAML：gap_limitup_hot_theme.yaml

文件：`strategies/gap_limitup_hot_theme.yaml`

### 13.1 策略定位

在现有 `gap_limitup_breakout` 的基础上，叠加热点题材主线条件。

### 13.2 策略定义建议

```yaml
name: gap_limitup_hot_theme
display_name: 跳空涨停+热点题材
description: 站上MA100，出现跳空突破或涨停突破，同时命中今日热点主线题材的强势股。
category: momentum
core_rules: [1, 3]
required_tools:
  - get_daily_history
  - get_realtime_quote
  - search_stock_news

screening:
  filters:
    - field: above_ma100
      op: "=="
      value: true
    - field: is_hot_theme_stock
      op: "=="
      value: true
    - field: theme_heat_score
      op: ">="
      value: 70
    - field: hot_momentum_triggered
      op: "=="
      value: true
  scoring:
    - field: theme_heat_score
      weight: 30
      cap: 100
    - field: theme_match_score
      weight: 25
      cap: 1.0
    - field: volume_ratio
      weight: 15
      cap: 5.0
    - field: breakout_ratio
      weight: 15
    - field: trend_score
      weight: 10
    - field: liquidity_score
      weight: 5

instructions: |
  本策略用于筛选“热点题材主线 + 强势技术形态”共振个股。

  入选重点：
  1. 股价位于 MA100 上方
  2. 属于今日高热度题材主线
  3. 量价配合良好
  4. 具备跳空突破、涨停突破或近似强势突破形态

  AI 二筛时应重点判断：
  - 是否为题材主线前排
  - 是龙头、补涨还是跟风
  - 新闻催化是否真实存在
```

---

## 14. CandidateAnalysisService 的改造

文件：`src/services/candidate_analysis_service.py`

### 14.1 为什么这里必须继续复用现有新闻能力

因为它已经是项目现有的 AI 二筛新闻入口：

- 会调用 `search_stock_news(...)`
- 会保存 `save_news_intel(...)`
- 与 `analysis_service.py` 联动成熟

所以新方案不是取代它，而是加强它。

---

### 14.2 建议改造目标

把“全局题材上下文”带入 top K 候选 AI 二筛。

### 14.3 方法签名建议

从：

```python
def analyze_top_k(self, candidates, top_k, news_top_m=None):
```

改为：

```python
def analyze_top_k(
    self,
    candidates,
    top_k,
    news_top_m=None,
    theme_context=None,
):
```

### 14.4 每个 candidate 新增上下文

```python
candidate_theme_context = {
    "primary_theme": ...,
    "theme_heat_score": ...,
    "theme_match_score": ...,
    "theme_match_reasons": ...,
    "theme_event_types": ...,
}
```

### 14.5 AI 分析联动方案

有两种实现路径：

#### 路线 A：轻量版（推荐第一版）
保持 `AnalysisService.analyze_stock(...)` 不动，只在返回结果上附加题材信息。

优点：
- 改动小
- 风险低

缺点：
- AI 不会真正利用题材上下文做推理

#### 路线 B：增强版（推荐第二步）
扩展 `AnalysisService` / pipeline，让题材上下文进入 prompt。

建议第一版先做 A，第二版再做 B。

### 14.6 候选股新闻层保持不变但要强调其作用

这里继续调用：

```python
response = self.search_service.search_stock_news(
    stock_code=code,
    stock_name=name or code,
    max_results=5,
)
```

它的作用变成：
- 对全局题材层做个股验证
- 检查是否存在订单/公告/事件/涨停原因
- 帮助 AI 判断龙头/补涨/跟风

即：

> **全局热点层负责“题材是什么”，个股新闻层负责“这只股为什么跟这个题材有关”。**

---

## 15. 配置改造

文件：`src/config.py`

建议新增配置项：

```python
hot_theme_enabled: bool = False
hot_theme_force_refresh: bool = False
hot_theme_fail_open: bool = True
hot_theme_top_n: int = 5
hot_theme_min_heat_score: float = 70.0
hot_theme_min_match_score: float = 0.6
hot_theme_cache_dir: str = "data/theme_context"
hot_theme_include_content_excerpt: bool = False
hot_theme_core_platforms: list[str] = ["baidu", "weibo", "zhihu", "36kr", "wallstreetcn", "bbc"]
hot_theme_optional_platforms: list[str] = ["cls", "thepaper", "jiemian", "yicai", "people", "cctv", "huxiu"]
```

并补充环境变量读取：

- `HOT_THEME_ENABLED`
- `HOT_THEME_FORCE_REFRESH`
- `HOT_THEME_FAIL_OPEN`
- `HOT_THEME_TOP_N`
- `HOT_THEME_MIN_HEAT_SCORE`
- `HOT_THEME_MIN_MATCH_SCORE`
- `HOT_THEME_CACHE_DIR`

---

## 16. OpenClaw Skill 的正确接法（旁路方案）

虽然 DSA 主链路不直接依赖 skill，但为了充分利用你当前已有的新闻 skill 能力，建议增加一个**旁路接入方案**。

### 16.1 旁路方案的定位

作为以下用途：

1. 开发阶段验证热点 query 组合
2. 旁路生成每日新闻 JSON
3. 当 DSA 内部 SearchService 结果不足时，人工/定时补充

### 16.2 旁路产物格式建议

OpenClaw 侧每日生成：

```text
/mnt/e/daily_stock_analysis/data/theme_context/
  external_hotspot_news_YYYY-MM-DD.json
```

结构与 `HotspotNewsBundle` 尽量兼容。

### 16.3 DSA 读取方式

`ThemeContextService` 可增加可选读取：

```python
if external_cache_exists:
    merge_external_hotspot_news(...)
```

### 16.4 边界说明

- 这是增强能力，不是主依赖
- 外部 skill 数据缺失时，DSA 仍可仅依赖内部 `SearchService` 正常运行

---

## 17. 测试设计

### 17.1 SearchService 新方法测试

新增测试：
- `tests/test_search_service_topic_news.py`
- `tests/test_search_service_hotspot_feed.py`

覆盖：
- query 组装
- provider failover
- 空结果/错误结果
- 多 query 聚合去重

### 17.2 HotspotSearchService 测试

新增：
- `tests/test_hotspot_search_service.py`

覆盖：
- 多平台搜索聚合
-