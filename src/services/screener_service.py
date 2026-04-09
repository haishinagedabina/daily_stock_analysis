from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import pandas as pd

from src.config import get_config

logger = logging.getLogger(__name__)


@dataclass
class ScreeningCandidateRecord:
    code: str
    name: str
    rank: int
    rule_score: float
    rule_hits: List[str]
    factor_snapshot: Dict[str, Any]
    matched_strategies: List[str] = field(default_factory=list)
    strategy_scores: Dict[str, float] = field(default_factory=dict)
    # ── 五层决策字段 (Phase 2A) ──
    setup_type: Optional[str] = None
    strategy_family: Optional[str] = None
    trade_stage: Optional[str] = None
    entry_maturity: Optional[str] = None
    risk_level: Optional[str] = None
    market_regime: Optional[str] = None
    theme_position: Optional[str] = None
    candidate_pool_level: Optional[str] = None
    trade_plan_json: Optional[str] = None


@dataclass
class ScreeningEvaluationResult:
    selected: List[ScreeningCandidateRecord]
    rejected: List[Dict[str, Any]]


class ScreenerService:
    """规则首筛服务。

    Operates in two modes:
    - **Strategy mode** (skill_manager provided): delegates evaluation to
      StrategyScreeningEngine using YAML-defined rules.
    - **Legacy mode** (no skill_manager): backward-compatible hardcoded rules
      for trend-volume-breakout screening.
    """

    def __init__(
        self,
        min_list_days: Optional[int] = None,
        min_volume_ratio: Optional[float] = None,
        min_avg_amount: Optional[float] = None,
        breakout_lookback_days: Optional[int] = None,
        skill_manager: Optional[Any] = None,
        strategy_names: Optional[List[str]] = None,
    ) -> None:
        self._skill_manager = skill_manager
        self._strategy_names = strategy_names
        self._use_strategy_engine = skill_manager is not None

        self.min_list_days = min_list_days if min_list_days is not None else _config_attr("screening_min_list_days", 120)
        self.min_volume_ratio = min_volume_ratio if min_volume_ratio is not None else _config_attr("screening_min_volume_ratio", 1.2)
        self.min_avg_amount = min_avg_amount if min_avg_amount is not None else _config_attr("screening_min_avg_amount", 50_000_000)
        self.breakout_lookback_days = breakout_lookback_days if breakout_lookback_days is not None else _config_attr("screening_breakout_lookback_days", 20)

    def screen(
        self,
        snapshot_df: pd.DataFrame,
        candidate_limit: Optional[int] = None,
    ) -> List[ScreeningCandidateRecord]:
        """返回按得分排序后的候选列表。"""
        if candidate_limit is None:
            candidate_limit = _config_attr("screening_candidate_limit", 30)
        return self.evaluate(snapshot_df).selected[:candidate_limit]

    def evaluate(
        self,
        snapshot_df: pd.DataFrame,
        prefiltered_rules: Optional[List] = None,
    ) -> ScreeningEvaluationResult:
        """输出入选候选与淘汰原因。

        Parameters
        ----------
        snapshot_df : DataFrame
            因子快照。
        prefiltered_rules : list, optional
            外部预过滤的 StrategyScreeningRule 列表。提供时直接使用这些规则，
            跳过内部 skill_manager 查询——用于五层管线的策略事前过滤 (D5)。
        """
        if prefiltered_rules is not None:
            return self._evaluate_with_engine(snapshot_df, rules_override=prefiltered_rules)
        if self._use_strategy_engine:
            return self._evaluate_with_engine(snapshot_df)
        return self._evaluate_legacy(snapshot_df)

    # ── Strategy engine path ─────────────────────────────────────────────

    def _evaluate_with_engine(
        self,
        snapshot_df: pd.DataFrame,
        rules_override: Optional[List] = None,
    ) -> ScreeningEvaluationResult:
        from src.services.strategy_screening_engine import (
            CommonFilterConfig,
            StrategyScreeningEngine,
            build_rules_from_skills,
        )

        if snapshot_df is None or snapshot_df.empty:
            return ScreeningEvaluationResult(selected=[], rejected=[])

        if rules_override is not None:
            rules = rules_override
        else:
            skills = self._skill_manager.get_screening_rules(
                strategy_names=self._strategy_names,
            )
            if not skills:
                logger.warning("No screening strategies found; falling back to legacy mode")
                return self._evaluate_legacy(snapshot_df)
            rules = build_rules_from_skills(skills)
        engine = StrategyScreeningEngine()
        common = CommonFilterConfig(
            exclude_st=True,
            min_list_days=self.min_list_days,
            min_avg_amount=self.min_avg_amount,
        )
        result = engine.evaluate(
            snapshot_df=snapshot_df,
            rules=rules,
            common_filters=common,
        )

        selected = [
            ScreeningCandidateRecord(
                code=c.code,
                name=c.name,
                rank=c.rank,
                rule_score=c.final_score,
                rule_hits=c.rule_hits,
                factor_snapshot=c.factor_snapshot,
                matched_strategies=c.matched_strategies,
                strategy_scores=c.strategy_scores,
                setup_type=c.setup_type,
                strategy_family=c.strategy_family,
            )
            for c in result.selected
        ]
        return ScreeningEvaluationResult(selected=selected, rejected=result.rejected)

    # ── Legacy path (backward compatible) ────────────────────────────────

    def _evaluate_legacy(self, snapshot_df: pd.DataFrame) -> ScreeningEvaluationResult:
        if snapshot_df is None or snapshot_df.empty:
            return ScreeningEvaluationResult(selected=[], rejected=[])

        selected: List[ScreeningCandidateRecord] = []
        rejected: List[Dict[str, Any]] = []

        for row in snapshot_df.to_dict("records"):
            reasons = self._collect_rejection_reasons(row)
            if reasons:
                rejected.append({
                    "code": row.get("code"),
                    "name": row.get("name"),
                    "rejection_reasons": reasons,
                })
                continue

            rule_hits = self._build_rule_hits(row)
            score = self._score(row, rule_hits)
            selected.append(
                ScreeningCandidateRecord(
                    code=str(row.get("code", "")),
                    name=str(row.get("name", "")),
                    rank=0,
                    rule_score=score,
                    rule_hits=rule_hits,
                    factor_snapshot=dict(row),
                )
            )

        selected.sort(key=lambda item: item.rule_score, reverse=True)
        for idx, item in enumerate(selected, start=1):
            item.rank = idx

        return ScreeningEvaluationResult(selected=selected, rejected=rejected)

    def _collect_rejection_reasons(self, row: Dict[str, Any]) -> List[str]:
        reasons: List[str] = []

        if bool(row.get("is_st", False)):
            reasons.append("st_filtered")
        if float(row.get("days_since_listed") or 0) < self.min_list_days:
            reasons.append("listed_days_below_threshold")
        if float(row.get("avg_amount") or 0.0) < self.min_avg_amount:
            reasons.append("liquidity_below_threshold")
        if not self._is_trend_aligned(row):
            reasons.append("trend_not_aligned")
        if float(row.get("volume_ratio") or 0.0) < self.min_volume_ratio:
            reasons.append("volume_below_threshold")

        return reasons

    @staticmethod
    def _is_trend_aligned(row: Dict[str, Any]) -> bool:
        close = float(row.get("close") or 0.0)
        ma5 = float(row.get("ma5") or 0.0)
        ma10 = float(row.get("ma10") or 0.0)
        ma20 = float(row.get("ma20") or 0.0)
        return close >= ma20 and ma5 >= ma10 >= ma20 and ma20 > 0

    def _build_rule_hits(self, row: Dict[str, Any]) -> List[str]:
        hits: List[str] = []

        if self._is_trend_aligned(row):
            hits.append("trend_aligned")
        if float(row.get("volume_ratio") or 0.0) >= self.min_volume_ratio:
            hits.append("volume_expanding")
        if float(row.get("breakout_ratio") or 0.0) >= 0.995:
            hits.append("near_breakout")
        if float(row.get("avg_amount") or 0.0) >= self.min_avg_amount:
            hits.append("liquidity_ok")

        return hits

    @staticmethod
    def _score(row: Dict[str, Any], rule_hits: List[str]) -> float:
        score = 0.0
        if "trend_aligned" in rule_hits:
            score += 40.0
        if "volume_expanding" in rule_hits:
            score += 30.0
        if "near_breakout" in rule_hits:
            score += 20.0
        if "liquidity_ok" in rule_hits:
            score += 10.0

        breakout_ratio = max(float(row.get("breakout_ratio") or 0.0) - 1.0, 0.0)
        score += breakout_ratio * 1000
        score += min(float(row.get("volume_ratio") or 0.0), 3.0)
        return round(score, 2)


def _config_attr(attr: str, default: Any) -> Any:
    """Safely read a config attribute with fallback."""
    try:
        config = get_config()
        return getattr(config, attr, default)
    except Exception:
        return default
