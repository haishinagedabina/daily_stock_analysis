# OpenClaw 热点题材筛选接口文档

## 概述

DSA（Daily Stock Analysis）为 OpenClaw 提供专用接口，用于触发"极端强势组合"策略的筛选运行。OpenClaw 负责收集热点新闻并提炼题材，DSA 负责从题材出发进行后续筛选。

---

## 接口定义

### 端点

```
POST /api/v1/screening/openclaw-theme-run
```

### 请求头

```
Content-Type: application/json
Authorization: Bearer <token>  # 如需认证
```

---

## 请求体

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

### 字段说明

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `trade_date` | string | ✅ | 交易日期，格式 YYYY-MM-DD |
| `market` | string | ✅ | 市场代码，第一版仅支持 `cn` |
| `themes` | array | ✅ | 热点题材数组，不能为空 |
| `options` | object | ❌ | 筛选选项 |

### Theme 对象

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `name` | string | ✅ | 题材名称，如"机器人"、"芯片" |
| `heat_score` | number | ✅ | 热度评分，0-100 |
| `confidence` | number | ✅ | 置信度，0-1 |
| `catalyst_summary` | string | ✅ | 催化剂摘要，简述利好原因 |
| `keywords` | array | ✅ | 关键词列表，用于股票匹配 |
| `evidence` | array | ❌ | 证据列表（新闻、公告等） |

### Evidence 对象

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `title` | string | ✅ | 新闻标题 |
| `source` | string | ✅ | 信息来源 |
| `url` | string | ❌ | 原文链接 |
| `published_at` | string | ❌ | 发布时间，ISO 8601 格式 |

### Options 对象

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `candidate_limit` | number | 50 | 候选上限 |
| `ai_top_k` | number | 10 | AI 分析数量 |
| `force_refresh` | boolean | false | 是否强制刷新 |

---

## 响应体

### 成功响应 (200 OK)

```json
{
  "run_id": "run_20260326_001",
  "status": "queued",
  "strategy_names": ["extreme_strength_combo"],
  "accepted_theme_count": 1,
  "created_at": "2026-03-26T09:01:23+08:00"
}
```

### 响应字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `run_id` | string | 筛选运行 ID，用于查询结果 |
| `status` | string | 运行状态，初始为 `queued` |
| `strategy_names` | array | 策略名称，固定为 `["extreme_strength_combo"]` |
| `accepted_theme_count` | number | 接受的题材数量 |
| `created_at` | string | 创建时间，ISO 8601 格式 |

### 错误响应

#### 400 Bad Request - 无效请求

```json
{
  "error": "themes cannot be empty",
  "code": "invalid_themes"
}
```

#### 400 Bad Request - 不支持的市场

```json
{
  "error": "market must be 'cn' in phase 1",
  "code": "unsupported_market"
}
```

#### 400 Bad Request - 无效日期格式

```json
{
  "error": "trade_date must be in YYYY-MM-DD format",
  "code": "invalid_date_format"
}
```

#### 500 Internal Server Error

```json
{
  "error": "Internal server error",
  "code": "internal_error"
}
```

---

## 使用示例

### cURL

```bash
curl -X POST http://localhost:8000/api/v1/screening/openclaw-theme-run \
  -H "Content-Type: application/json" \
  -d '{
    "trade_date": "2026-03-26",
    "market": "cn",
    "themes": [
      {
        "name": "机器人",
        "heat_score": 90,
        "confidence": 0.85,
        "catalyst_summary": "政策催化",
        "keywords": ["人形机器人", "丝杠"],
        "evidence": []
      }
    ],
    "options": {
      "candidate_limit": 50,
      "ai_top_k": 10
    }
  }'
```

### Python

```python
import requests
import json

url = "http://localhost:8000/api/v1/screening/openclaw-theme-run"

payload = {
    "trade_date": "2026-03-26",
    "market": "cn",
    "themes": [
        {
            "name": "机器人",
            "heat_score": 90,
            "confidence": 0.85,
            "catalyst_summary": "政策催化",
            "keywords": ["人形机器人", "丝杠"],
            "evidence": []
        }
    ],
    "options": {
        "candidate_limit": 50,
        "ai_top_k": 10
    }
}

response = requests.post(url, json=payload)
result = response.json()
print(f"Run ID: {result['run_id']}")
```

### JavaScript

```javascript
const payload = {
  trade_date: "2026-03-26",
  market: "cn",
  themes: [
    {
      name: "机器人",
      heat_score: 90,
      confidence: 0.85,
      catalyst_summary: "政策催化",
      keywords: ["人形机器人", "丝杠"],
      evidence: []
    }
  ],
  options: {
    candidate_limit: 50,
    ai_top_k: 10
  }
};

const response = await fetch("http://localhost:8000/api/v1/screening/openclaw-theme-run", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(payload)
});

const result = await response.json();
console.log(`Run ID: ${result.run_id}`);
```

---

## 查询结果

获得 `run_id` 后，可通过以下接口查询筛选结果：

### 查询运行状态

```
GET /api/v1/screening/runs/{run_id}
```

### 查询候选结果

```
GET /api/v1/screening/runs/{run_id}/candidates
```

---

## 核心约束

1. **市场限制**：第一版仅支持 `market: "cn"`
2. **题材必需**：`themes` 数组不能为空
3. **策略固定**：返回的 `strategy_names` 始终为 `["extreme_strength_combo"]`
4. **日期格式**：`trade_date` 必须为 YYYY-MM-DD 格式
5. **阈值**：题材匹配度需达到 0.80 以上才能进入候选池

---

## 筛选逻辑

### 硬门槛

- 股票必须匹配至少一个外部热点题材（匹配度 >= 0.80）

### 评分模型

- **基础分**：MA100 之上 (+20)
- **主信号**：低位123、跳空涨停、涨停、底背离 (+12-15 each)
- **辅助加分**：龙头特征、热度、量能 (+0-15)

### 入选标准

- **正式入选**：极端强势分 >= 80
- **观察名单**：极端强势分 60-80

---

## 最佳实践

1. **题材质量**：确保 `heat_score` 和 `confidence` 准确反映题材热度
2. **关键词精准**：提供 3-5 个高相关性关键词，避免过于宽泛
3. **催化摘要**：简明扼要说明利好原因，便于后续 AI 分析
4. **证据完整**：提供新闻链接和发布时间，增强可信度
5. **调用频率**：建议盘前或盘中定时调用，避免频繁重复

---

## 常见问题

### Q: 如何判断筛选是否完成？

A: 通过 `GET /api/v1/screening/runs/{run_id}` 查询 `status` 字段。当 `status` 为 `completed` 或 `completed_with_ai_degraded` 时表示完成。

### Q: 候选数量为 0 是什么原因？

A: 可能原因：
1. 题材匹配度不足（< 0.80）
2. 匹配的股票没有满足强势信号条件
3. 市场当日没有符合条件的股票

### Q: 是否支持多个题材同时筛选？

A: 支持。在 `themes` 数组中添加多个题材对象即可。

### Q: 结果中的"命中原因"是什么？

A: 显示该股票满足的强势信号，如"MA100之上"、"跳空突破"、"涨停"等。

---

## 版本信息

- **API 版本**：v1
- **发布日期**：2026-03-26
- **支持市场**：A股 (cn)
- **策略**：极端强势组合 (extreme_strength_combo)

---

## 联系方式

如有问题或建议，请联系 DSA 开发团队。
