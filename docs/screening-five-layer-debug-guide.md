# 选股五层 Debug 手册

本文档用于在不额外改代码的前提下，通过 Cursor / VSCode Debug 方式排查 `L1-L5` 选股链路，重点观察每一步的输入、输出与质量是否符合预期。

适用目标：
- 排查为什么某次运行 `0 candidates`
- 排查为什么 `L2` 没有热点板块 / 主线题材
- 排查为什么 `D5` 放行策略过少
- 排查为什么首筛后没有候选或大量被拒绝
- 排查为什么 `L3/L4/L5` 把候选降级到 `watch` 或直接否决

相关主文件：
- `src/services/screening_task_service.py`
- `src/services/five_layer_pipeline.py`
- `src/services/screener_service.py`
- `src/services/market_environment_engine.py`
- `src/services/strategy_dispatcher.py`
- `src/services/setup_resolver.py`
- `src/services/candidate_pool_classifier.py`
- `src/services/trade_stage_judge.py`

## 使用方式

这份手册按统一格式编排：

1. 先看 `Debug 位置（文件 + 行号）`
2. 再看这几个位置对应的 `排查点`
3. 如果某一层已经明显异常，就先停在这一层，不要继续往下查

一句话口诀：

`先看总控，再看 L1，再看 L2，再看 D5，再看首筛，最后看 L3-L5`

## 总控：先判断是否值得继续往下查

### Debug 位置（文件 + 行号）

- `src/services/screening_task_service.py:367-379`
  - 这里生成 `market_env` 和 `regime_candidate_cap`
- `src/services/screening_task_service.py:563-624`
  - 这里计算 `effective_limit`，决定是否跳过 screening，并汇总 `pipeline_stats`

### 排查点

- `snapshot_df` 是否为空或数量异常小
- `market_env.regime` 是否符合当天盘面直觉
- `regime_candidate_cap` 是否已经把候选上限压缩
- `effective_limit == 0` 吗
- `selected_count`、`rejected_count`、`kept_count`、`vetoed_count` 是否合理

### 快速结论

- 如果 `effective_limit == 0`，后面的 `L2-L5` 都不会执行
- 如果 `snapshot_df` 很小，优先查同步 / 因子快照，不要先怀疑五层逻辑

## L1：市场环境层

### Debug 位置（文件 + 行号）

- `src/services/screening_task_service.py:367-379`
  - runtime 主链路调用 `env_engine.assess(...)`
- `src/services/market_environment_engine.py:38-62`
  - `assess()` 最终产出 `MarketEnvironment`
- `src/services/market_environment_engine.py:82-144`
  - 赚钱效应、涨跌比、`regime` 判定细节

### 排查点

- `guard_result.is_safe`
- `guard_result.index_price`
- `guard_result.index_ma100`
- `market_stats`
- `market_env.regime`
- `market_env.risk_level`
- `market_env.message`

### 重点判断

- `market_stats` 是否为空或明显异常
- 指数价格和 `MA100` 是否正常
- `regime` 是否符合当天盘面直觉
- `defensive / stand_aside` 是否被误判得过早

### 常见异常

- 明明是中性盘面，但 `regime` 被打成 `defensive`
- `regime_candidate_cap` 被压到 `0`
- `market_stats` 降级为空，导致环境误判

## L2：板块热度、题材聚合与缩圈

### Debug 位置（文件 + 行号）

- `src/services/five_layer_pipeline.py:144-166`
  - `SectorHeatEngine.compute_all_sectors(...)`，看板块热度总览
- `src/services/five_layer_pipeline.py:177-196`
  - `ThemeAggregationService.aggregate(...)` 和 `ThemePositionResolver(...)`
- `src/services/five_layer_pipeline.py:198-243`
  - `get_main_theme_boards()` 与 `theme_universe_df` 缩圈
- `src/services/theme_position_resolver.py:137-142`
  - `get_main_theme_boards()`
- `src/services/theme_position_resolver.py:149-169`
  - `resolve(...)` 的主线优先匹配入口

### 排查点

- `len(all_sector_results)`
- `len(sector_results)`
- `stats["sector_status_counts"]`
- `theme_results`
- `theme_resolver.identified_themes`
- `main_theme_boards`
- `theme_member_candidate_count`
- `l2_filter_mode`
- `len(theme_universe_df)`

### 重点判断

- `all_sector_results` 太少，优先怀疑板块映射或成员数据不完整
- `hot=0` 但 `warm` 很多，不一定是 bug，可能只是阈值偏严
- `identified_themes` 为空，优先怀疑主线识别规则过严
- `main_theme_boards` 有值但 `member_codes` 为空，优先怀疑板块成员映射问题
- `theme_shrink` 后样本极少，优先怀疑主线成员覆盖太窄

### 常见异常

- 明显强势板块被打成 `neutral/cold`
- 只有 `warm` 没有 `hot`，并且完全没有主线
- `l2_filter_mode == "theme_fallback_insufficient_candidates"`，说明缩圈后样本不足，被迫回退

## D5：策略前置过滤

### Debug 位置（文件 + 行号）

- `src/services/five_layer_pipeline.py:255-285`
  - 主链路里构建全部规则并执行 `get_allowed_rules(...)`
- `src/services/strategy_dispatcher.py:69-114`
  - `filter_strategies(...)`，看单票策略被挡掉了哪些
- `src/services/strategy_dispatcher.py:116-173`
  - `get_allowed_rules(...)` 和 `_is_allowed(...)`，看事前规则过滤

### 排查点

- `market_env.regime`
- `len(all_rules)`
- `len(prefiltered_rules or [])`
- `allowed_rule_names`
- `blocked_rule_names`
- 某条关键策略的 `system_role`
- 某条关键策略的 `strategy_family`
- 某条关键策略的 `applicable_market`

### 重点判断

- `defensive` 下 `allowed_rules` 是否少得不合理
- 预期应保留的 `entry_core` 策略是否被提前拦截
- `skill_manager.get_screening_rules()` 返回的策略集合是否完整

### 常见异常

- D5 过严，导致首筛前就只剩极少数策略
- 某条非动量核心策略在 `defensive` 环境被错误挡掉

## 首筛：规则引擎阶段

### Debug 位置（文件 + 行号）

- `src/services/five_layer_pipeline.py:292-306`
  - `screener_service.evaluate(...)` 返回后，直接看 selected / rejected 总览
- `src/services/screener_service.py:79-96`
  - `evaluate(...)` 入口
- `src/services/screener_service.py:100-160`
  - `_evaluate_with_engine(...)`，看公共过滤和策略引擎结果

### 排查点

- `theme_universe_df.shape`
- `self.min_list_days`
- `evaluation.rejected[*].rejection_reasons`
- `evaluation.selected`
- `evaluation.rejected`
- `stats["screening_rejection_reason_counts"]`

### 重点判断

- 首筛最关键不是“哪些命中了”，而是“为什么大量被拒绝”
- 当前公共硬过滤只剩上市天数 / `ST`；`avg_amount` 已不再在这一层直接淘汰股票
- 如果怀疑成交额约束仍在生效，优先检查具体策略规则或后续链路，而不是首筛公共配置
- 是否大量没有任何策略命中
- 是否因为公共过滤条件在命中规则前就被淘汰

### 常见异常

- `snapshot_df` 明明有数据，但 `evaluation.selected == []`
- 拒绝原因高度单一，通常说明阈值过严或快照字段缺失
- `factor_snapshot` 缺关键字段，导致统一误杀

## L3：候选池分级

### Debug 位置（文件 + 行号）

- `src/services/five_layer_pipeline.py:418-426`
  - 主链路里调用 `pool_classifier.classify(...)`
- `src/services/candidate_pool_classifier.py:39-74`
  - `classify(...)` 的分级规则

### 排查点

- `candidate.code`
- `fs["leader_score"]`
- `fs["extreme_strength_score"]`
- `tp`
- `pool_level`

### 重点判断

- 强票却被归到 `watchlist`，通常是 `leader_score`、`extreme_strength_score` 或 `theme_position` 不合理
- 大量股票都落在 `watchlist`，优先往前追 `factor_snapshot` 和 `theme_position`

## L4：买点识别与成熟度

### Debug 位置（文件 + 行号）

- `src/services/five_layer_pipeline.py:367-382`
  - `dispatcher.filter_strategies(...)` 后进入 `setup_resolver.resolve(...)`
- `src/services/five_layer_pipeline.py:414-416`
  - `EntryMaturityAssessor.assess(...)` 和 `SetupFreshnessAssessor.assess(...)`
- `src/services/setup_resolver.py:86-153`
  - `resolve(...)` 的 setup 收敛逻辑

### 排查点

- `candidate.matched_strategies`
- `dispatch_result.allowed_strategies`
- `candidate.strategy_scores`
- `resolution.setup_type`
- `resolution.strategy_family`
- `entry_mat`
- `setup_freshness`

### 重点判断

- 有策略命中但 `setup_type == NONE`，优先怀疑 `SetupResolver` 收敛过严
- `setup_type` 正确但 `entry_maturity` 很低，说明买点成熟度不足
- 本该是趋势突破，却被收敛成其它 setup，要重点看 `strategy_scores` 与 resolver 优先级

## L5：交易阶段裁决

### Debug 位置（文件 + 行号）

- `src/services/five_layer_pipeline.py:430-447`
  - `TradeStageJudge.judge(...)` 和 `TradePlanBuilder.build(...)`
- `src/services/trade_stage_judge.py:30-98`
  - `judge(...)` 的硬门控、阶段上限与正向裁决
- `src/services/trade_plan_builder.py:122-155`
  - `build(...)` 的交易计划生成规则

### 排查点

- `st`
- `entry_mat`
- `pool_level`
- `tp`
- `has_stop`
- `trade_stage`
- `trade_plan`

### 重点判断

- `trade_stage in {"reject", "stand_aside"}` 才会被正式否决
- `watch` 不会被 veto，但说明质量不够进入执行态
- `probe_entry` / `add_on_strength` 才是值得重点关注的可执行候选

### 常见异常

- setup 看起来不错，但因为 `theme_position=non_theme` 被压到 `watch`
- 没有止损条件，导致阶段被打低
- 大量股票都卡在 `stand_aside`，优先回查 `L1 + L3/L4`

## 全局 Watch 表达式

建议把这些表达式固定放进 Debug 的 watch 面板：

- `market_env.regime if market_env else None`
- `market_env.risk_level if market_env else None`
- `effective_limit`
- `len(snapshot_df) if snapshot_df is not None else None`
- `len(all_sector_results) if 'all_sector_results' in locals() else None`
- `len(sector_results) if 'sector_results' in locals() else None`
- `main_theme_boards if 'main_theme_boards' in locals() else None`
- `len(theme_universe_df) if 'theme_universe_df' in locals() else None`
- `len(prefiltered_rules) if 'prefiltered_rules' in locals() and prefiltered_rules is not None else None`
- `len(evaluation.selected) if 'evaluation' in locals() else None`
- `len(evaluation.rejected) if 'evaluation' in locals() else None`
- `stats if 'stats' in locals() else None`
- `candidate.code if 'candidate' in locals() else None`
- `candidate.matched_strategies if 'candidate' in locals() else None`
- `candidate.setup_type if 'candidate' in locals() else None`
- `candidate.theme_position if 'candidate' in locals() else None`
- `candidate.candidate_pool_level if 'candidate' in locals() else None`
- `candidate.trade_stage if 'candidate' in locals() else None`

## 最终结果判断

进入单票循环后，最后重点看两组结果：

- `kept`
- `vetoed`

推荐观察：

- `len(kept)`
- `len(vetoed)`
- `[(c.code, c.trade_stage, c.theme_position, c.candidate_pool_level, c.setup_type) for c in kept[:20]]`
- `[(c.code, c.trade_stage, c.setup_type) for c in vetoed[:20]]`

判断方式：

- `selected_before_l345 == 0`：问题主要在 `L2/D5/首筛`
- `selected_before_l345 > 0` 但 `kept == 0`：问题主要在 `L3/L4/L5`
- `kept > 0` 但几乎全是 `watch`：问题不是“无候选”，而是“质量不足进入执行态”

## 排查模板

建议每次排查都按下面模板记录，避免重复定位：

```md
## Screening Debug 记录

- run_id:
- trade_date:
- market_regime:
- risk_level:
- effective_limit:

### L1
- guard_result:
- market_stats 是否完整:
- 是否触发 regime_cap:

### L2
- total_sectors:
- hot_warm_sectors:
- sector_status_counts:
- identified_themes:
- main_theme_boards:
- l2_filter_mode:
- universe_before / universe_after:

### D5
- total_rules:
- allowed_rules:
- blocked_rules:
- 被误杀的关键策略:

### 首筛
- selected_before_l345:
- rejected_before_l345:
- top rejection reasons:
- 被错误拒绝的样本:

### L3/L4/L5
- kept_count:
- vetoed_count:
- trade_stage_counts:
- theme_position_counts:
- setup_type_counts:
- 重点观察股票:

### 初步结论
- 最可疑层级:
- 根因假设:
- 下一步验证:
```

## 推荐使用方式

- 第一轮只看总量和分布，不要一开始就盯一只股票
- 第二轮只抽 3-5 只“你认为应该入选但没入选”的股票做单票追踪
- 每次只验证一个假设，例如“L2 热度阈值过严”或“D5 defensive 过严”，不要同时改多个判断
- 如果问题表现为 `0 candidates`，优先看 `effective_limit`、`allowed_rules`、`selected_before_l345`

## 与现有日志配合

当前代码里已经有一些辅助日志，调试时可优先对照这些统计：

- `pipeline L2 sectors`
- `pipeline L2 themes`
- `pipeline L2 universe`
- `pipeline D5`
- `pipeline screening`
- `pipeline L3-L5`
- `screening_run event=five_layer_pipeline_done`
- `screening_run event=stage_completed`

但日志只用来快速定位层级，真正判断质量时仍建议以断点和 watch 变量为准。
