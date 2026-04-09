# -*- coding: utf-8 -*-
"""
FiveLayerPipeline — L2 前置过滤 + 策略事前控制 + L3/L4/L5 逐票否决。

核心流程:
  L1 (Phase 1 已前置于 execute_run) →
  L2 板块热度 + 主线识别 → 缩小 universe →
  策略前置过滤 (D5) → 选股 →
  L3/L4/L5 逐票裁决（否决权）→
  五层优先级排序

D1 修复: 五层从"后置标注"翻转为"前置过滤 + 逐票否决"。
D3 修复: 先识别主线题材，再匹配股票（由 ThemePositionResolver 实现）。
D5 修复: 选股前过滤策略（由 StrategyDispatcher.get_allowed_rules 实现）。
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Dict, List, Optional, Set

import pandas as pd

from src.schemas.trading_types import (
    CandidatePoolLevel,
    MarketEnvironment,
    MarketRegime,
    SetupType,
    ThemePosition,
    TradeStage,
)
from src.services.screener_service import ScreeningCandidateRecord, ScreenerService

logger = logging.getLogger(__name__)

# ── 五层优先级排序权重 ──────────────────────────────────────────────────────
_STAGE_PRIORITY: Dict[str, int] = {
    "add_on_strength": 100,
    "probe_entry": 80,
    "focus": 40,
    "watch": 10,
    "stand_aside": 0,
    "reject": -50,
}

_POOL_PRIORITY: Dict[str, int] = {
    "leader_pool": 30,
    "focus_list": 15,
    "watchlist": 0,
}

_THEME_PRIORITY: Dict[str, int] = {
    "main_theme": 20,
    "secondary_theme": 10,
    "follower_theme": 0,
    "fading_theme": -10,
    "non_theme": -20,
}

# L2 universe 缩小: 主线板块候选不足时的最低阈值
MIN_THEME_CANDIDATES = 10


@dataclass
class PipelineResult:
    """FiveLayerPipeline 输出。"""
    candidates: List[ScreeningCandidateRecord]
    decision_context: Dict[str, Any]
    market_env: MarketEnvironment
    pipeline_stats: Dict[str, Any] = field(default_factory=dict)


class FiveLayerPipeline:
    """L2 前置过滤 → 策略前置控制 → 选股 → L3/L4/L5 逐票否决。"""

    def run(
        self,
        snapshot_df: pd.DataFrame,
        trade_date: date,
        market_env: MarketEnvironment,
        guard_result: Any,
        screener_service: ScreenerService,
        candidate_limit: int,
        db_manager: Any,
        theme_context: Optional[Any] = None,
        skill_manager: Optional[Any] = None,
    ) -> PipelineResult:
        stats: Dict[str, Any] = {
            "universe_before": len(snapshot_df),
        }

        # ── L2: 板块热度计算 ──────────────────────────────────────────
        from src.services.sector_heat_engine import SectorHeatEngine
        from src.services.theme_aggregation_service import ThemeAggregationService
        from src.services.theme_position_resolver import ThemePositionResolver
        from src.services.theme_mapping_registry import ThemeMappingRegistry

        sector_results = []
        all_sector_results = []
        try:
            sector_engine = SectorHeatEngine(db_manager=db_manager)
            all_sector_results = sector_engine.compute_all_sectors(snapshot_df, trade_date)
            sector_results = [
                s for s in all_sector_results
                if s.sector_status in ("hot", "warm")
            ]
        except Exception as exc:
            logger.warning("pipeline L2 SectorHeatEngine failed (degraded): %s", exc)

        stats["total_sectors"] = len(all_sector_results)
        stats["hot_warm_sectors"] = len(sector_results)

        # ── L2: 题材聚合 + 主线识别 ──────────────────────────────────
        theme_registry = None
        try:
            theme_registry = ThemeMappingRegistry()
            if theme_registry.is_empty:
                logger.warning("pipeline: ThemeMappingRegistry loaded 0 mappings")
        except Exception as exc:
            logger.warning("pipeline ThemeMappingRegistry failed: %s", exc)

        theme_results = []
        try:
            agg_service = ThemeAggregationService(registry=theme_registry)
            theme_results = agg_service.aggregate(sector_results)
        except Exception as exc:
            logger.warning("pipeline L2 ThemeAggregation failed: %s", exc)
            theme_registry = None

        theme_ctx_dict = None
        if theme_context is not None:
            theme_ctx_dict = self._serialize_theme_context(theme_context)

        theme_resolver = ThemePositionResolver(
            sector_results, theme_results, theme_ctx_dict, registry=theme_registry,
        )

        # ── L2: Universe 缩小（仅主线/次线板块的成员） ────────────────
        main_theme_boards = theme_resolver.get_main_theme_boards()
        theme_universe_df = snapshot_df

        if main_theme_boards:
            member_codes = self._get_theme_member_codes(db_manager, main_theme_boards)
            if member_codes:
                mask = snapshot_df["code"].isin(member_codes)
                theme_filtered = snapshot_df[mask].copy()

                if len(theme_filtered) >= MIN_THEME_CANDIDATES:
                    theme_universe_df = theme_filtered
                    logger.info(
                        "pipeline L2 universe shrink: %d → %d (boards=%d)",
                        len(snapshot_df), len(theme_universe_df), len(main_theme_boards),
                    )
                else:
                    logger.info(
                        "pipeline L2: theme candidates=%d < min=%d, using full universe",
                        len(theme_filtered), MIN_THEME_CANDIDATES,
                    )

        stats["universe_after_l2"] = len(theme_universe_df)

        # ── 策略前置过滤 (D5) ─────────────────────────────────────────
        prefiltered_rules = None
        all_rules = None

        if skill_manager is not None:
            try:
                from src.services.strategy_screening_engine import build_rules_from_skills
                from src.services.strategy_dispatcher import StrategyDispatcher

                skills = skill_manager.get_screening_rules()
                if skills:
                    all_rules = build_rules_from_skills(skills)
                    dispatcher = StrategyDispatcher(all_rules)
                    prefiltered_rules = dispatcher.get_allowed_rules(
                        all_rules, market_env.regime,
                    )
                    stats["total_rules"] = len(all_rules)
                    stats["allowed_rules"] = len(prefiltered_rules)
                    logger.info(
                        "pipeline D5: regime=%s total_rules=%d allowed=%d",
                        market_env.regime.value,
                        len(all_rules),
                        len(prefiltered_rules),
                    )
            except Exception as exc:
                logger.warning("pipeline D5 strategy pre-filter failed: %s", exc)

        # ── 选股（在缩小的 universe + 过滤后的策略上执行）─────────────
        evaluation = screener_service.evaluate(
            theme_universe_df,
            prefiltered_rules=prefiltered_rules,
        )
        selected = evaluation.selected[:candidate_limit]
        stats["selected_before_l345"] = len(selected)

        if not selected:
            return PipelineResult(
                candidates=[],
                decision_context=self._build_decision_context(
                    market_env, guard_result, sector_results, theme_registry,
                ),
                market_env=market_env,
                pipeline_stats=stats,
            )

        # ── L3/L4/L5 逐票裁决 ────────────────────────────────────────
        from src.services.candidate_pool_classifier import CandidatePoolClassifier
        from src.services.setup_resolver import SetupResolver
        from src.services.entry_maturity_assessor import EntryMaturityAssessor
        from src.services.trade_stage_judge import TradeStageJudge
        from src.services.strategy_dispatcher import StrategyDispatcher
        from src.services.trade_plan_builder import TradePlanBuilder

        all_codes = [c.code for c in selected]
        board_map = db_manager.batch_get_instrument_board_names(all_codes)

        pool_classifier = CandidatePoolClassifier()
        maturity_assessor = EntryMaturityAssessor()
        stage_judge = TradeStageJudge()
        plan_builder = TradePlanBuilder()

        dispatcher = None
        setup_resolver = None
        if all_rules:
            try:
                dispatcher = StrategyDispatcher(all_rules)
                setup_resolver = SetupResolver(all_rules)
            except Exception as exc:
                logger.warning("pipeline: dispatcher/resolver init failed: %s", exc)

        vetoed: List[ScreeningCandidateRecord] = []
        kept: List[ScreeningCandidateRecord] = []

        for candidate in selected:
            fs = candidate.factor_snapshot or {}
            stock_boards = board_map.get(candidate.code, [])

            # L2: 题材地位
            theme_decision = theme_resolver.resolve(stock_boards)
            tp = theme_decision.theme_position

            # Phase 2B: 策略调度 + 买点收敛
            if dispatcher is not None and setup_resolver is not None:
                dispatch_result = dispatcher.filter_strategies(
                    candidate.matched_strategies or [], market_env.regime,
                )
                resolution = setup_resolver.resolve(
                    allowed_strategies=dispatch_result.allowed_strategies,
                    strategy_scores=candidate.strategy_scores or {},
                    market_regime=market_env.regime,
                    theme_position=tp,
                )
                st = resolution.setup_type
                candidate.setup_type = st.value if st != SetupType.NONE else None
                candidate.strategy_family = (
                    resolution.strategy_family.value if resolution.strategy_family else None
                )
                candidate.matched_strategies = dispatch_result.allowed_strategies
            else:
                try:
                    st = SetupType(candidate.setup_type) if candidate.setup_type else SetupType.NONE
                except ValueError:
                    st = SetupType.NONE

            # L4: 买点成熟度
            entry_mat = maturity_assessor.assess(st, fs)

            # L3: 候选池分级
            leader_score = float(fs.get("leader_score", 0.0))
            extreme_strength = float(fs.get("extreme_strength_score", 0.0))
            pool_level = pool_classifier.classify(
                leader_score=leader_score,
                extreme_strength_score=extreme_strength,
                theme_position=tp,
                market_regime=market_env.regime,
            )

            # L5: 交易阶段裁决
            has_stop = bool(fs.get("has_stop_loss", False))
            trade_stage = stage_judge.judge(
                env=market_env,
                setup_type=st,
                entry_maturity=entry_mat,
                pool_level=pool_level,
                theme_position=tp,
                has_stop_loss=has_stop,
            )

            # Phase 3A: 交易计划
            trade_plan = plan_builder.build(
                trade_stage=trade_stage,
                setup_type=st,
                entry_maturity=entry_mat,
                risk_level=market_env.risk_level,
                pool_level=pool_level,
                factor_snapshot=fs,
            )

            # 写回 candidate
            candidate.trade_stage = trade_stage.value
            candidate.market_regime = market_env.regime.value
            candidate.entry_maturity = entry_mat.value
            candidate.candidate_pool_level = pool_level.value
            candidate.theme_position = tp.value
            candidate.risk_level = market_env.risk_level.value
            if trade_plan is not None:
                candidate.trade_plan_json = json.dumps(
                    {
                        "initial_position": trade_plan.initial_position,
                        "add_rule": trade_plan.add_rule,
                        "stop_loss_rule": trade_plan.stop_loss_rule,
                        "take_profit_plan": trade_plan.take_profit_plan,
                        "invalidation_rule": trade_plan.invalidation_rule,
                        "risk_level": trade_plan.risk_level.value,
                        "holding_expectation": trade_plan.holding_expectation,
                    },
                    ensure_ascii=False,
                )

            # ── D1 核心: L5 否决权 ────────────────────────────────────
            if trade_stage in (TradeStage.REJECT, TradeStage.STAND_ASIDE):
                vetoed.append(candidate)
            else:
                kept.append(candidate)

        stats["vetoed_count"] = len(vetoed)
        stats["kept_count"] = len(kept)
        logger.info(
            "pipeline L3-L5: %d kept, %d vetoed (reject/stand_aside)",
            len(kept), len(vetoed),
        )

        # ── 五层优先级排序 (D6) ───────────────────────────────────────
        for c in kept:
            stage_p = _STAGE_PRIORITY.get(c.trade_stage or "", 0)
            pool_p = _POOL_PRIORITY.get(c.candidate_pool_level or "", 0)
            theme_p = _THEME_PRIORITY.get(c.theme_position or "", 0)
            c.rule_score = stage_p + pool_p + theme_p + c.rule_score * 0.01

        kept.sort(key=lambda c: c.rule_score, reverse=True)
        for i, c in enumerate(kept, 1):
            c.rank = i

        if kept:
            logger.info(
                "pipeline rerank top3: %s",
                [(c.code, round(c.rule_score, 1), c.trade_stage, c.theme_position) for c in kept[:3]],
            )

        # ── 构建 decision_context ─────────────────────────────────────
        decision_context = self._build_decision_context(
            market_env, guard_result, sector_results, theme_registry,
        )
        decision_context["pipeline_stats"] = stats

        return PipelineResult(
            candidates=kept,
            decision_context=decision_context,
            market_env=market_env,
            pipeline_stats=stats,
        )

    # ── 内部方法 ─────────────────────────────────────────────────────

    @staticmethod
    def _get_theme_member_codes(
        db_manager: Any, board_names: Set[str],
    ) -> Set[str]:
        """从 DB 获取板块成员代码集合。"""
        member_map = db_manager.batch_get_board_member_codes(
            list(board_names), market="cn",
        )
        codes: Set[str] = set()
        for members in member_map.values():
            codes.update(members)
        return codes

    @staticmethod
    def _build_decision_context(
        market_env: MarketEnvironment,
        guard_result: Any,
        sector_results: list,
        theme_registry: Any,
    ) -> Dict[str, Any]:
        return {
            "market_environment": {
                "market_regime": market_env.regime.value,
                "risk_level": market_env.risk_level.value,
                "index_price": getattr(market_env, "index_price", None),
                "index_ma100": getattr(market_env, "index_ma100", None),
                "is_safe": guard_result.is_safe if guard_result else None,
                "message": guard_result.message if guard_result else None,
            },
            "sector_heat_results": [
                {
                    "board_name": s.board_name,
                    "board_type": s.board_type,
                    "sector_hot_score": s.sector_hot_score,
                    "sector_status": s.sector_status,
                    "sector_stage": s.sector_stage,
                    "canonical_theme": (
                        theme_registry.resolve_tag(s.board_name) if theme_registry else s.board_name
                    ),
                    "stock_count": s.stock_count,
                    "up_count": s.up_count,
                    "limit_up_count": getattr(s, "limit_up_count", 0),
                }
                for s in sector_results
            ],
            "hot_theme_count": sum(1 for s in sector_results if s.sector_status == "hot"),
            "warm_theme_count": sum(1 for s in sector_results if s.sector_status == "warm"),
        }

    @staticmethod
    def _serialize_theme_context(theme_context: Any) -> Dict[str, Any]:
        themes = []
        for theme in getattr(theme_context, "themes", []) or []:
            themes.append({
                "name": getattr(theme, "name", None),
                "heat_score": getattr(theme, "heat_score", 0.0),
                "confidence": getattr(theme, "confidence", 0.0),
            })
        return {"themes": themes}
