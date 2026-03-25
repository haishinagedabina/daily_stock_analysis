# 底背离双突破策略设计文档

**日期：** 2026-03-25

**状态：** 方案已在对话中确认，待进入实现计划阶段

## 一、背景

当前仓库已经具备以下相关能力：

- `src/indicators/divergence_detector.py`
  负责基于 `MACD histogram` 的经典背离识别
- `src/indicators/trendline_detector.py`
  负责下降趋势线拟合与突破识别
- `src/indicators/low_123_trendline_detector.py`
  负责低位 `123 + 趋势线` 联合识别
- `src/services/factor_service.py`
  负责将结构识别结果转为筛股因子
- `src/strategies/entry_strategies.py`
  负责将指标/结构识别封装为入场策略

但当前仓库还不具备一套严格符合以下业务定义的新策略：

- 底背离必须严格依据 `MACD` 黄白线 `DIF/DEA` 的低点关系识别
- 六种底背离细分形态全部纳入候选范围
- 最终买点不是“背离出现”本身，而是“底背离 + 下降趋势线突破 + 水平阻力线突破”的联合确认
- 返回结果必须明确标注命中的具体形态，便于后续分形态回测

这意味着现有 `histogram` 背离逻辑不能直接复用为主检测逻辑，只能保留为现有功能的一部分，不能替代新策略。

## 二、目标

新增一套“底背离双突破策略”，满足以下目标：

- 严格基于 `DIF/DEA` 识别底背离，不使用 `histogram` 替代
- 覆盖六种细分形态，并在结果中返回唯一形态标签
- 使用底背离作为前置过滤，使用双突破作为最终触发
- 输出结构化结果，供筛股、策略、回测、日志、图表复用
- 优先复用现有 swing low/high、趋势线和筛股基础设施，避免平行实现

## 三、非目标

本次设计明确不做以下事情：

- 不修改现有 `src/indicators/divergence_detector.py` 的既有语义
- 不重写整个趋势线检测体系
- 不在本轮引入数据库 schema 迁移去持久化所有新扩展因子
- 不在本轮确定所有阈值的最终最佳参数
- 不把回测参数优化混进首次实现

## 四、已确认需求

以下需求已在对话中确认：

- 该策略必须和双突破一起使用
- 六种底背离形态都要纳入候选
- 结果中必须注明满足哪一种形态
- 底背离必须严格以 `DIF/DEA` 低点关系为准
- 具体参数调节延后到回测阶段，不在本轮拍板

## 五、总体方案

推荐采用“新增专用联合检测器 + 接入现有筛股与策略体系”的方式推进。

### 方案原则

- 保持现有 `histogram` 背离 detector 稳定，不直接改造
- 新增一个专门负责 `DIF/DEA` 六形态底背离 + 双突破确认的 detector
- 将该 detector 输出接入 `FactorService`
- 新增对应 YAML 策略，接入 `screening`
- 在 `entry_strategies.py` 中增加新的策略封装，便于复用

### 方案优点

- 语义清晰，不混淆两套背离定义
- 便于单独测试六种形态与双突破确认
- 便于后续按形态分组回测
- 最大限度减少对既有功能的回归风险

## 六、识别模型

### 1. 核心结构

新策略采用如下四段式识别流程：

1. 找到价格低点对 `A/B`
2. 在 `A/B` 附近匹配 `DIF/DEA` 低点对 `a/b`
3. 判断价格关系与黄白线关系，映射到六种形态之一
4. 在底背离成立后，继续检查“下降趋势线突破 + 水平阻力线突破”是否同步确认

### 2. 价格低点对 `A/B`

`A/B` 不是任意两个低点，而是满足以下约束的一组结构低点：

- `A` 和 `B` 都必须是 swing low
- `A.idx < B.idx`
- 两者之间至少相隔最小 bars 数，避免噪音拆点
- `A` 到 `B` 之间必须存在一个明确反弹高点 `H`
- `B` 必须足够新，避免识别陈旧结构

### 3. 黄白线低点对 `a/b`

`a/b` 必须严格由 `DIF/DEA` 两条线共同确认：

- 在 `A` 附近窗口中寻找 `DIF` 和 `DEA` 的局部低点，构成 `a`
- 在 `B` 附近窗口中寻找 `DIF` 和 `DEA` 的局部低点，构成 `b`
- 只有当 `DIF` 与 `DEA` 低点出现在同一小窗口内时，才视为有效黄白线低点
- 如果 `DIF` 和 `DEA` 在方向判定上相互冲突，则该候选直接丢弃

### 4. 三态关系

价格关系三态：

- `down`
- `flat`
- `up`

黄白线关系三态：

- `up`
- `flat`
- `down`

其中 `flat` 不是完全相等，而是基于容差区间判定。具体阈值在实现计划阶段给出默认值，并明确标记为后续回测可调参数。

### 5. 六种有效形态

本策略只保留以下六种候选：

- `price_down_macd_up`
- `price_down_macd_flat`
- `price_flat_macd_up`
- `price_flat_macd_down`
- `price_up_macd_down`
- `price_up_macd_flat`

每次命中必须返回：

- `pattern_code`
- `pattern_label`
- `price_relation`
- `macd_relation`

## 七、上下文门控

为减少误识别，形态识别之前必须先做上下文门控。

### 1. 底部反转型门控

针对以下家族：

- `price_down_*`
- `price_flat_*`

要求结构前存在明确下跌背景，例如：

- 最近一段 swing high 呈下降结构
- 局部斜率为负
- 短中期均线偏弱

### 2. 强势回撤型门控

针对以下家族：

- `price_up_macd_down`
- `price_up_macd_flat`

要求结构前先有明显上涨，再发生回撤。否则极易把普通横盘或杂波误判为强势回撤型底背离。

## 八、双突破确认

底背离本身不构成最终买点。最终触发必须满足双突破确认。

### 1. 水平阻力线

水平阻力线默认使用 `A/B` 之间的近期反弹高点 `H`。

确认条件：

- 收盘价有效突破 `H`

### 2. 下降趋势线

下降趋势线使用与当前结构直接相关的 swing high 拟合，要求：

- 仅使用当前这组结构前后的相关高点
- 斜率必须为负
- 至少有 2 个有效触点
- 触点数量越多，质量越高

确认条件：

- 收盘价有效突破该趋势线在当前 bar 的投影值

### 3. 同步窗口

最终 `confirmed` 必须满足：

- 水平阻力线突破
- 下降趋势线突破
- 两者发生在同一 bar 或极小同步窗口内

如二者相隔过大，则降级为：

- `late_or_weak`

如果仅底背离成立但突破未完成，则返回：

- `divergence_only`
或
- `structure_ready`

具体状态命名在实现时统一，不允许含义重叠。

## 九、结果输出 schema

建议 detector 统一输出如下结构：

```python
{
    "found": bool,
    "state": "rejected" | "divergence_only" | "structure_ready" | "confirmed" | "late_or_weak",
    "pattern_family": "price_down" | "price_flat" | "price_up" | None,
    "pattern_code": str | None,
    "pattern_label": str | None,
    "price_relation": "down" | "flat" | "up" | None,
    "macd_relation": "down" | "flat" | "up" | None,
    "price_low_a": {"idx": int, "price": float} | None,
    "price_low_b": {"idx": int, "price": float} | None,
    "macd_low_a": {"idx": int, "dif": float, "dea": float} | None,
    "macd_low_b": {"idx": int, "dif": float, "dea": float} | None,
    "rebound_high": {"idx": int, "price": float} | None,
    "horizontal_resistance": float | None,
    "downtrend_line": {
        "found": bool,
        "slope": float,
        "intercept": float,
        "touch_points": list[dict],
        "touch_count": int,
        "breakout_bar_index": int | None,
        "projected_value_at_breakout": float | None,
        "breakout_confirmed": bool,
    } | None,
    "horizontal_breakout_confirmed": bool,
    "trendline_breakout_confirmed": bool,
    "double_breakout_sync": bool,
    "entry_price": float | None,
    "stop_loss_price": float | None,
    "signal_strength": float,
    "rejection_reason": str | None,
}
```

## 十、仓库接入点

### 1. 新增文件

- `src/indicators/bottom_divergence_breakout_detector.py`

职责：

- 计算或消费 `DIF/DEA`
- 生成价格低点对与黄白线低点对
- 完成六形态分类
- 检查双突破确认
- 输出统一结构化结果

### 2. 修改文件

- `src/services/factor_service.py`
- `src/strategies/entry_strategies.py`
- `strategies/README.md`
- `README.md`
- `docs/CHANGELOG.md`

### 3. 新增策略文件

- `strategies/bottom_divergence_double_breakout.yaml`

建议筛股条件：

- 过滤：`bottom_divergence_double_breakout == true`
- 打分：`bottom_divergence_signal_strength + volume_ratio + trend_score + liquidity_score`

## 十一、因子输出设计

建议在 `FactorService` 中新增以下因子：

- `bottom_divergence_double_breakout`
- `bottom_divergence_state`
- `bottom_divergence_pattern_code`
- `bottom_divergence_pattern_label`
- `bottom_divergence_signal_strength`
- `bottom_divergence_entry_price`
- `bottom_divergence_stop_loss`
- `bottom_divergence_horizontal_breakout`
- `bottom_divergence_trendline_breakout`
- `bottom_divergence_sync_breakout`

### 关于持久化的设计取舍

本轮不扩 `daily_factor_snapshots` 固定表结构。

原因：

- 当前策略筛股链路中，候选结果已经持有 `factor_snapshot_json`
- 新形态标签与结构结果可以随候选记录一起保留
- 避免为了首次上线策略引入无关数据库迁移

如果后续需要做“全市场、全量、历史日级”的形态统计，再单独设计 schema 扩展。

## 十二、策略封装设计

建议在 `src/strategies/entry_strategies.py` 中新增一个独立策略封装，而不是复用 Strategy B。

原因：

- `Low123TrendlineDetector` 和“底背离双突破策略”是两套不同结构
- 语义拆开后更利于回测和调试
- 避免污染现有 Strategy B 的行为边界

该策略类建议只在以下情况下触发：

- detector 返回 `state == confirmed`

并直接返回：

- `pattern_code`
- `pattern_label`
- `entry_price`
- `stop_loss_price`
- `signal_strength`

## 十三、测试策略

本功能必须按 TDD 实现。

### 1. detector 单元测试

新增：

- `tests/test_bottom_divergence_breakout_detector.py`

至少覆盖：

- 六种形态各 1 个正例
- 只背离不突破
- 只突破不背离
- 双突破不同步
- `DIF` / `DEA` 方向不一致时拒绝
- 价格噪音导致伪低点时拒绝
- 强势回撤型在无前置上涨背景时拒绝
- 底部反转型在无前置下跌背景时拒绝

### 2. FactorService 测试

新增：

- `tests/test_factor_service_bottom_divergence.py`

至少覆盖：

- 新因子全部存在
- `pattern_code` 正常透传
- 短数据安全降级
- `confirmed` 与布尔因子一致

### 3. entry strategy 测试

新增或修改：

- `tests/test_entry_strategies.py`

至少覆盖：

- 新策略类可导入
- 只有 `confirmed` 才触发
- `entry_price` 与 `stop_loss_price` 正确返回

### 4. YAML / screening 联动测试

至少覆盖：

- 新字段可被 `strategy_screening_engine` 正确读取
- YAML 过滤条件和打分逻辑有效

## 十四、参数策略

以下参数在首次实现中给出默认值，但明确不在本轮确认最佳值：

- swing low / swing high 识别窗口
- `A/B` 最小间隔 bars
- `flat` 容差
- `A/B` 与 `a/b` 的配对窗口
- 双突破同步窗口
- 趋势线触点容差
- 信号强度打分权重

这些参数在设计上必须满足：

- 有默认值
- 代码中有清晰命名
- 测试中固定默认值保证稳定
- 后续回测可以单独调优

## 十五、风险与缓解

### 风险 1：误把震荡结构识别为底背离

缓解：

- 强制上下文门控
- 强制 `H` 存在
- 强制 `DIF/DEA` 方向一致
- 强制双突破确认

### 风险 2：对强势回撤型过滤过严导致漏检

缓解：

- 将“前置上涨背景”写成清晰、可调的独立门控
- 参数调优延后到回测阶段

### 风险 3：结果无法支撑后续分形态回测

缓解：

- `pattern_code` 作为一级字段返回
- 因子输出层透传 `pattern_code`
- YAML 策略名称与 detector 输出保持一致

### 风险 4：修改既有 detector 导致回归

缓解：

- 不修改现有 `histogram` detector 的语义
- 新增专用 detector

## 十六、验收标准

满足以下条件即可认为本设计实现完成：

- 能稳定识别六种底背离候选
- 最终买点只在“双突破确认”后触发
- 每次命中结果都带 `pattern_code`
- `FactorService` 能输出对应筛股因子
- 新 YAML 策略能进入现有 `screening` 体系
- 新增测试覆盖六形态、误判反例和联动路径
- 文档同步更新，说明新策略能力与使用方式

## 十七、实施顺序建议

1. 先写 detector 的失败测试
2. 实现六形态识别
3. 再实现双突破确认
4. 接入 `FactorService`
5. 新增 YAML 策略
6. 新增 entry strategy 封装
7. 更新 README 与 CHANGELOG

## 十八、说明

本设计文档刻意将“策略定义是否正确”和“参数是否最优”拆开处理。

当前阶段先把结构定义、检测边界、结果 schema 和接入路径定准；
参数最优化交给后续回测阶段完成。
