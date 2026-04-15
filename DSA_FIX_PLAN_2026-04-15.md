# DSA 选股算法修复方案

> 对应审计报告：DSA_ALGORITHM_AUDIT_2026-04-15.md
> 涉及文件：7个（4个YAML + 2个Python + 1个config）
> 原则：最小改动、向后兼容、不改数据库schema

---

## 修复1：volume_breakout 追高防护 + 打分修正

### 1a. 添加乖离率过滤（YAML filter）

**文件**：`strategies/volume_breakout.yaml`

```yaml
# 现有 filters 末尾追加：
screening:
  filters:
    - field: breakout_ratio
      op: ">="
      value: 0.995
    - field: volume_ratio
      op: ">="
      value: 2.0
    - field: trend_score
      op: ">="
      value: 40
    - field: close_strength
      op: ">="
      value: 0.5
    # ✅ 新增：乖离率防追高（instructions 要求 < 5%）
    - field: ma5_distance_pct
      op: "<="
      value: 8.0
```

> **说明**：instructions 写 5%，但实战中考虑到科创板/创业板 20cm 波动，放宽到 8%。如果要严格执行 instructions 就用 5.0。

### 1b. 修正 bonus_multiplier 爆炸问题（YAML scoring）

**文件**：`strategies/volume_breakout.yaml`

```yaml
  scoring:
    - field: breakout_ratio
      weight: 40
      bonus_above: 1.0
      bonus_multiplier: 50      # ← 从 1000 改为 50（超出1.0每1%加0.5分，而非10分）
      cap: 1.15                 # ✅ 新增：超过1.15不再额外加分
    - field: volume_ratio
      weight: 30
      cap: 5.0
    - field: trend_score
      weight: 20
    - field: liquidity_score
      weight: 10
```

> **效果**：breakout_ratio=1.15 时，原来得分 = 40 + 150 = 190 分；改后 = 40 + (0.15×50) = 47.5 分。回到合理范围。

---

## 修复2：common_filter 增加大阴线过滤

**文件**：`src/services/strategy_screening_engine.py`

**改动位置**：`CommonFilterConfig` dataclass + `apply_common_filters()` 方法

```python
# ── 修改 CommonFilterConfig ──
@dataclass(frozen=True)
class CommonFilterConfig:
    exclude_st: bool = True
    min_list_days: int = 120
    # ✅ 新增
    exclude_big_yin: bool = True          # 排除当日大阴线
    max_negative_pct_chg: float = -5.0    # 当日跌幅超过此值则排除
    min_close_strength: float = 0.15      # 收盘强度最低门槛（0=收在最低价）


# ── 修改 apply_common_filters() ──
def apply_common_filters(
    self, row: Dict[str, Any], config: CommonFilterConfig
) -> List[str]:
    reasons: List[str] = []
    if config.exclude_st and bool(row.get("is_st", False)):
        reasons.append("st_filtered")
    if float(row.get("days_since_listed") or 0) < config.min_list_days:
        reasons.append("listed_days_below_threshold")

    # ✅ 新增：大阴线过滤
    if config.exclude_big_yin:
        pct_chg = float(row.get("pct_chg") or 0)
        close_strength = float(row.get("close_strength") or 1)
        candle = str(row.get("candle_pattern", ""))
        if pct_chg < config.max_negative_pct_chg:
            reasons.append("big_drop_filtered")
        if close_strength < config.min_close_strength and pct_chg < 0:
            reasons.append("weak_close_filtered")
        if candle == "big_yin":
            reasons.append("big_yin_candle_filtered")

    return reasons
```

> **效果**：中嘉博创（pct_chg=-9.88, close_strength=0.0, candle=big_yin）会被3条规则同时拦截。

---

## 修复3a：gap_limitup_breakout 的 `or:` 语法 bug

### 方案A（推荐）：修改 YAML 用正确语法

**文件**：`strategies/gap_limitup_breakout.yaml`

```yaml
screening:
  filters:
    - field: above_ma100
      op: "=="
      value: true
    # ✅ 修正：用 any: 替代无效的 or:
    - any:
        - field: gap_breakaway
          op: "=="
          value: true
        - field: limit_up_breakout
          op: "=="
          value: true
  scoring:
    - field: volume_ratio
      weight: 40
      cap: 5.0
    - field: breakout_ratio
      weight: 30
      bonus_above: 1.0
      bonus_multiplier: 50       # ← 同步修复 multiplier
      cap: 1.15
    - field: trend_score
      weight: 20
    - field: liquidity_score
      weight: 10
```

### 方案B（可选补充）：让引擎兼容 `or:` 语法

**文件**：`src/services/strategy_screening_engine.py`，`_parse_filter_node()` 函数

```python
def _parse_filter_node(raw: Any) -> Optional[FilterNode]:
    if not isinstance(raw, dict):
        return None

    # ✅ 新增：处理 field+op+or 的混合写法
    # 当一个 filter item 同时有 field/op 和 or: 时，
    # 将自身作为第一个条件，or: 列表作为其他条件，组成 any 组
    if "field" in raw and "op" in raw and "or" in raw:
        main_cond = FilterCondition(
            field=raw["field"],
            op=raw["op"],
            value=raw.get("value"),
            value_ref=raw.get("value_ref"),
        )
        or_items = raw["or"]
        if isinstance(or_items, list):
            children = [main_cond]
            for item in or_items:
                parsed = _parse_filter_node(item)
                if parsed is not None:
                    children.append(parsed)
            return FilterGroup(mode="any", conditions=children)

    if "field" in raw and "op" in raw:
        return FilterCondition(
            field=raw["field"],
            op=raw["op"],
            value=raw.get("value"),
            value_ref=raw.get("value_ref"),
        )
    for mode in ("all", "any"):
        items = raw.get(mode)
        if isinstance(items, list):
            children = [
                parsed
                for item in items
                for parsed in [_parse_filter_node(item)]
                if parsed is not None
            ]
            return FilterGroup(mode=mode, conditions=children)
    return None
```

> **建议**：两个都做。方案A确保当前YAML正确，方案B防止未来同类错误静默失败。

---

## 修复3b：dragon_head / bull_trend 定位明确化

这两个策略**本质是 AI 分析提示词**，不是量化筛选规则。有两个选择：

### 选项1（推荐）：明确标注为非筛选策略

**文件**：`strategies/dragon_head.yaml` 和 `strategies/bull_trend.yaml`

在两个文件中各添加：

```yaml
# 注意：本策略无 screening 定义，仅用于 AI 分析指导。
# 不参与 strategy_screening_engine 的量化筛选流程。
screening_disabled: true   # 标记为非筛选策略（可选，引擎本身会跳过无 screening 的策略）
```

### 选项2：补充 screening 定义

如果确实希望它们参与筛选，需要为每个策略设计量化 filter。例如 bull_trend：

```yaml
screening:
  filters:
    - field: ma5
      op: ">="
      value_ref: ma10
    - field: ma10
      op: ">="
      value_ref: ma20
    - field: trend_score
      op: ">="
      value: 60
    - field: ma5_distance_pct
      op: "<="
      value: 5.0
  scoring:
    - field: trend_score
      weight: 50
    - field: volume_ratio
      weight: 25
      cap: 5.0
    - field: liquidity_score
      weight: 25
```

> **建议**：先用选项1，避免引入更多未验证的策略。后续如果要激活，单独测试验证。

---

## 修复4：评分归一化 + system_role 权重

**文件**：`src/services/strategy_screening_engine.py`

### 4a. 策略级分数归一化

在 `_compute_strategy_score()` 中加入归一化：

```python
# ── 策略满分上限 ──
_STRATEGY_MAX_SCORE: float = 100.0

def _compute_strategy_score(
    self, rule: StrategyScreeningRule, row: Dict[str, Any]
) -> float:
    total = sum(self.evaluate_score_component(sw, row) for sw in rule.scoring)
    # ✅ 新增：归一化到 [0, 100]
    return round(min(total, _STRATEGY_MAX_SCORE), 2)
```

### 4b. system_role 加权求和

在 `_build_sorted_candidates()` 中修改 final_score 计算：

```python
# ── system_role 权重映射 ──
_ROLE_WEIGHT: Dict[str, float] = {
    "entry_core": 1.0,       # 核心入场信号，全权重
    "stock_pool": 0.8,       # 选股池策略
    "confirm": 0.5,          # 确认信号，半权重
    "observation": 0.3,      # 观察信号
    "bonus_signal": 0.2,     # 加分信号
}

@staticmethod
def _build_sorted_candidates(
    candidate_map: Dict[str, "_CandidateAccumulator"],
    candidate_limit: Optional[int],
    # ✅ 新增：接收 rules 用于获取 system_role
    rules: Optional[List[StrategyScreeningRule]] = None,
) -> List[CandidateResult]:
    # 构建 strategy_name → system_role 映射
    role_map: Dict[str, str] = {}
    if rules:
        for r in rules:
            role_map[r.strategy_name] = r.system_role or "entry_core"

    candidates: List[CandidateResult] = []
    for acc in candidate_map.values():
        # ✅ 修改：加权求和代替简单求和
        if acc.strategy_scores:
            final_score = sum(
                score * _ROLE_WEIGHT.get(role_map.get(sname, "entry_core"), 1.0)
                for sname, score in acc.strategy_scores.items()
            )
        else:
            final_score = 0.0

        # ... 其余不变
```

同时需要修改 `evaluate()` 中调用 `_build_sorted_candidates` 的地方，传入 `rules`：

```python
# evaluate() 方法中，约第225行：
selected = self._build_sorted_candidates(candidate_map, candidate_limit, rules=rules)
```

> **效果举例**：
> - 兴图新科：volume_breakout(confirm) 47.5分 × 0.5 = **23.75 分**
> - 中嘉博创：3个 entry_core 策略各 ~70 分 × 1.0 = **~207 分**
> - 排名逻辑更符合直觉：多个核心信号共振 >> 单个确认信号很强

---

## 修复5：底背离信号时效性控制

**文件**：`strategies/bottom_divergence_double_breakout.yaml`

```yaml
screening:
  filters:
    - field: bottom_divergence_double_breakout
      op: "=="
      value: true
    # ✅ 新增：信号时效性门控
    # bottom_divergence_confirmation_days 表示双突破确认后经过的天数
    - field: bottom_divergence_confirmation_days
      op: "<="
      value: 10
  scoring:
    - field: bottom_divergence_signal_strength
      weight: 40
      cap: 1.0
    - field: volume_ratio
      weight: 25
      cap: 5.0
    - field: trend_score
      weight: 20
    - field: liquidity_score
      weight: 15
```

> **前提**：需要确认 `daily_factor_snapshots` 中已有 `bottom_divergence_confirmation_days` 字段。如果没有，需在因子计算层补充。

**检查方法**：

```sql
SELECT DISTINCT json_extract(factor_json, '$.bottom_divergence_confirmation_days')
FROM daily_factor_snapshots
WHERE json_extract(factor_json, '$.bottom_divergence_double_breakout') = 1
LIMIT 20;
```

如果字段不存在，需要在因子计算模块中补充（计算 `confirmation_date` 到 `trade_date` 的天数差）。这是一个上游改动，但逻辑简单。

---

## 修复6：shrink_pullback 支撑位确认

**文件**：`strategies/shrink_pullback.yaml`

```yaml
screening:
  filters:
    - field: ma5
      op: ">="
      value_ref: ma10
    - field: ma10
      op: ">="
      value_ref: ma20
    - field: volume_ratio
      op: "<="
      value: 0.7               # ← 从 0.8 收紧到 0.7（与 instructions 一致）
    - field: ma5_distance_pct
      op: "<="
      value: 2.0
    - field: pct_chg
      op: ">"
      value: 0
    # ✅ 新增：近3日有过回踩（最低价接近MA5/MA10）
    - field: pullback_touched_ma
      op: "=="
      value: true
  scoring:
    - field: trend_score
      weight: 40
    - field: volume_ratio
      weight: 30
      invert: true
      cap: 1.0
    - field: ma5_distance_pct
      weight: 20
      invert: true
      cap: 5.0
    - field: liquidity_score
      weight: 10
```

> **前提**：需在因子计算层新增 `pullback_touched_ma` 字段。逻辑：近3个交易日内，日内最低价是否触及 MA5（误差1%以内）或 MA10（误差2%以内）。

---

## 修复7：AI 二审覆盖率提升

**文件**：`src/services/screening_mode_registry.py`

```python
_SCREENING_MODE_PRESETS: Dict[str, Dict[str, Any]] = {
    "balanced": {},
    "aggressive": {
        "candidate_limit": 50,
        "ai_top_k": 25,           # ← 从 8 改为 25（50%覆盖率）
        "min_list_days": 60,
        "min_volume_ratio": 1.0,
        "breakout_lookback_days": 15,
        "factor_lookback_days": 60,
    },
    "quality": {
        "candidate_limit": 20,
        "ai_top_k": 10,           # ← 从 3 改为 10（50%覆盖率）
        "min_list_days": 180,
        "min_volume_ratio": 1.5,
        "breakout_lookback_days": 30,
        "factor_lookback_days": 120,
    },
}
```

**同时修改默认配置**：

**文件**：`src/config.py`（第554行）

```python
screening_ai_top_k: int = 10       # ← 从 5 改为 10
```

> **效果**：balanced 模式下 30 候选审 10 个（33%），aggressive 下 50 审 25（50%），quality 下 20 审 10（50%）。

---

## 修改文件总览

| 文件 | 修改内容 | 风险 |
|------|---------|------|
| `strategies/volume_breakout.yaml` | 加 ma5_distance_pct filter + 降 bonus_multiplier + 加 cap | 🟢 低 |
| `strategies/gap_limitup_breakout.yaml` | `or:` → `any:` + 降 bonus_multiplier | 🟢 低 |
| `strategies/bottom_divergence_double_breakout.yaml` | 加 confirmation_days filter | 🟡 中（依赖上游字段） |
| `strategies/shrink_pullback.yaml` | volume_ratio 收紧 + 加 pullback_touched_ma | 🟡 中（依赖上游字段） |
| `src/services/strategy_screening_engine.py` | common_filter 扩展 + or: 兼容 + 归一化 + role权重 | 🟡 中 |
| `src/services/screening_mode_registry.py` | ai_top_k 提升 | 🟢 低 |
| `src/config.py` | 默认 ai_top_k 提升 | 🟢 低 |

---

## 实施优先级

| 阶段 | 修复项 | 改动量 | 依赖 |
|------|--------|--------|------|
| **P0 立即** | 1a（乖离率filter）+ 1b（bonus_multiplier）+ 3a（or:→any:） | 3个YAML改几行 | 无 |
| **P0 立即** | 2（大阴线common_filter） | Python改20行 | 无 |
| **P1 本周** | 4（归一化+role权重）+ 7（ai_top_k） | Python改50行 + config改1行 | 无 |
| **P2 下周** | 5（底背离时效）+ 6（回踩确认） | YAML各1行 + 因子计算层新增字段 | 需先确认/补充上游因子 |
| **P3 择机** | 3b（dragon_head/bull_trend 定位） | YAML标注或补screening | 设计决策 |

---

## 预期效果（对比当前80条候选数据）

| 指标 | 修复前 | 修复后预估 |
|------|--------|-----------|
| 追高候选（ma5>10%） | 28条（35%） | ~3-5条（仅科创板20cm合理追高） |
| 涨停板入选 | 27条（34%） | ~8-12条（有跳空/底背离共振的优质涨停） |
| 大阴线入选 | ≥1条 | 0条 |
| 策略失效 | 4/12（33%） | 1/12（仅 dragon_head 待定） |
| AI二审覆盖 | 10% | 33-50% |
| volume_breakout 最高分 | 188分 | ≤50分 |
| 排名前5变化 | 追高股霸榜 | entry_core 多信号共振股优先 |
