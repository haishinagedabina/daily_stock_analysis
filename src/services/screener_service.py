from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import pandas as pd

from src.config import get_config


@dataclass
class ScreeningCandidateRecord:
    code: str
    name: str
    rank: int
    rule_score: float
    rule_hits: List[str]
    factor_snapshot: Dict[str, Any]


@dataclass
class ScreeningEvaluationResult:
    selected: List[ScreeningCandidateRecord]
    rejected: List[Dict[str, Any]]


class ScreenerService:
    """规则首筛服务。"""

    def __init__(
        self,
        min_list_days: Optional[int] = None,
        min_volume_ratio: Optional[float] = None,
        min_avg_amount: Optional[float] = None,
        breakout_lookback_days: Optional[int] = None,
    ) -> None:
        config = get_config()
        self.min_list_days = (
            min_list_days if min_list_days is not None else config.screening_min_list_days
        )
        self.min_volume_ratio = (
            min_volume_ratio if min_volume_ratio is not None else config.screening_min_volume_ratio
        )
        self.min_avg_amount = (
            min_avg_amount if min_avg_amount is not None else config.screening_min_avg_amount
        )
        self.breakout_lookback_days = (
            breakout_lookback_days
            if breakout_lookback_days is not None
            else config.screening_breakout_lookback_days
        )

    def screen(
        self,
        snapshot_df: pd.DataFrame,
        candidate_limit: Optional[int] = None,
    ) -> List[ScreeningCandidateRecord]:
        """返回按得分排序后的候选列表。"""
        if candidate_limit is None:
            candidate_limit = get_config().screening_candidate_limit
        return self.evaluate(snapshot_df).selected[:candidate_limit]

    def evaluate(self, snapshot_df: pd.DataFrame) -> ScreeningEvaluationResult:
        """输出入选候选与淘汰原因。"""
        if snapshot_df is None or snapshot_df.empty:
            return ScreeningEvaluationResult(selected=[], rejected=[])

        selected: List[ScreeningCandidateRecord] = []
        rejected: List[Dict[str, Any]] = []

        for row in snapshot_df.to_dict("records"):
            reasons = self._collect_rejection_reasons(row)
            if reasons:
                rejected.append(
                    {
                        "code": row.get("code"),
                        "name": row.get("name"),
                        "rejection_reasons": reasons,
                    }
                )
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
