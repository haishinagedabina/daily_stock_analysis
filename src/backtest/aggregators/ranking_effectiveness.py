# -*- coding: utf-8 -*-
"""Ranking effectiveness calculator for five-layer backtest.

Measures whether the screening system's tiered ranking (pool levels,
theme positions, maturity grades) actually predicts forward performance.

Key questions answered:
  - Does leader_pool outperform watchlist?
  - Does main_theme outperform non_theme?
  - Does HIGH maturity outperform MEDIUM / LOW?
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from src.backtest.models.backtest_models import FiveLayerBacktestGroupSummary
from src.backtest.utils.summary_metrics import get_aggregatable_sample_count

logger = logging.getLogger(__name__)

# ── Ranking pairs to compare ────────────────────────────────────────────────

_POOL_LEVEL_ORDER = ["leader_pool", "focus_list", "watchlist"]
_THEME_POSITION_ORDER = ["main_theme", "secondary_theme", "follower_theme", "non_theme"]
_MATURITY_ORDER = ["HIGH", "MEDIUM", "LOW"]


@dataclass(frozen=True)
class RankingComparisonResult:
    """Result of comparing two tiers within a dimension."""

    dimension: str
    tier_high: str
    tier_low: str
    high_avg_return: Optional[float]
    low_avg_return: Optional[float]
    excess_return_pct: Optional[float]
    high_win_rate: Optional[float]
    low_win_rate: Optional[float]
    high_sample_count: int
    low_sample_count: int
    is_effective: bool  # True if higher tier outperforms


@dataclass(frozen=True)
class RankingEffectivenessReport:
    """Full ranking effectiveness analysis."""

    comparisons: List[RankingComparisonResult]
    overall_effectiveness_ratio: float  # % of comparisons where ranking is effective
    top_k_hit_rate: Optional[float]
    excess_return_pct: Optional[float]
    ranking_consistency: Optional[float]


class RankingEffectivenessCalculator:
    """Evaluates whether the screening system's ranking tiers are predictive."""

    @staticmethod
    def compute(
        summaries: List[FiveLayerBacktestGroupSummary],
    ) -> RankingEffectivenessReport:
        """Compute ranking effectiveness from group summaries.

        Args:
            summaries: All group summaries for a run, including
                       candidate_pool_level, theme_position, entry_maturity groups.
        """
        index = _build_summary_index(summaries)
        comparisons: List[RankingComparisonResult] = []

        # Pool level comparisons
        comparisons.extend(
            _compare_tiers("candidate_pool_level", _POOL_LEVEL_ORDER, index),
        )

        # Theme position comparisons
        comparisons.extend(
            _compare_tiers("theme_position", _THEME_POSITION_ORDER, index),
        )

        # Maturity comparisons
        comparisons.extend(
            _compare_tiers("entry_maturity", _MATURITY_ORDER, index),
        )

        effective_count = sum(1 for c in comparisons if c.is_effective)
        total = len(comparisons) if comparisons else 1
        effectiveness_ratio = effective_count / total

        # Derive headline metrics from pool-level comparison
        top_k_hit_rate = _compute_top_k_hit_rate(index)
        excess_return = _compute_excess_return(index)
        consistency = _compute_ranking_consistency(comparisons)

        return RankingEffectivenessReport(
            comparisons=comparisons,
            overall_effectiveness_ratio=round(effectiveness_ratio, 4),
            top_k_hit_rate=top_k_hit_rate,
            excess_return_pct=excess_return,
            ranking_consistency=consistency,
        )


# ── Internal helpers ────────────────────────────────────────────────────────

def _build_summary_index(
    summaries: List[FiveLayerBacktestGroupSummary],
) -> Dict[str, Dict[str, FiveLayerBacktestGroupSummary]]:
    """Build {group_type: {group_key: summary}} lookup."""
    index: Dict[str, Dict[str, FiveLayerBacktestGroupSummary]] = {}
    for s in summaries:
        index.setdefault(s.group_type, {})[s.group_key] = s
    return index


def _compare_tiers(
    group_type: str,
    tier_order: List[str],
    index: Dict[str, Dict[str, FiveLayerBacktestGroupSummary]],
) -> List[RankingComparisonResult]:
    """Compare all available tier pairs within a dimension.

    Compares every pair (higher, lower) where both tiers have data,
    not just adjacent pairs — so leader_pool vs watchlist is compared
    even when focus_list is absent.
    """
    results: List[RankingComparisonResult] = []
    type_summaries = index.get(group_type, {})
    if not type_summaries:
        return results

    # Filter to tiers that have data, preserving rank order
    available = [t for t in tier_order if t in type_summaries]

    for i in range(len(available)):
        for j in range(i + 1, len(available)):
            high_key = available[i]
            low_key = available[j]
            high = type_summaries[high_key]
            low = type_summaries[low_key]

            h_ret = high.avg_return_pct
            l_ret = low.avg_return_pct
            excess = None
            is_effective = False
            if h_ret is not None and l_ret is not None:
                excess = round(h_ret - l_ret, 4)
                is_effective = h_ret > l_ret

            results.append(RankingComparisonResult(
                dimension=group_type,
                tier_high=high_key,
                tier_low=low_key,
                high_avg_return=h_ret,
                low_avg_return=l_ret,
                excess_return_pct=excess,
                high_win_rate=high.win_rate_pct,
                low_win_rate=low.win_rate_pct,
                high_sample_count=get_aggregatable_sample_count(high),
                low_sample_count=get_aggregatable_sample_count(low),
                is_effective=is_effective,
            ))
    return results


def _compute_top_k_hit_rate(
    index: Dict[str, Dict[str, FiveLayerBacktestGroupSummary]],
) -> Optional[float]:
    """% of leader_pool samples that are 'win' out of all wins."""
    pool_sums = index.get("candidate_pool_level", {})
    leader = pool_sums.get("leader_pool")
    if leader is None:
        return None

    total_samples = sum(
        get_aggregatable_sample_count(s) for s in pool_sums.values()
    )
    if total_samples == 0:
        return None

    leader_wr = (leader.win_rate_pct or 0) / 100
    leader_wins = leader_wr * get_aggregatable_sample_count(leader)

    total_wins = sum(
        ((s.win_rate_pct or 0) / 100) * get_aggregatable_sample_count(s)
        for s in pool_sums.values()
    )
    if total_wins == 0:
        return None

    return round(leader_wins / total_wins, 4)


def _compute_excess_return(
    index: Dict[str, Dict[str, FiveLayerBacktestGroupSummary]],
) -> Optional[float]:
    """leader_pool avg return - watchlist avg return."""
    pool_sums = index.get("candidate_pool_level", {})
    leader = pool_sums.get("leader_pool")
    watchlist = pool_sums.get("watchlist")
    if leader is None or watchlist is None:
        return None
    h = leader.avg_return_pct
    l = watchlist.avg_return_pct
    if h is None or l is None:
        return None
    return round(h - l, 4)


def _compute_ranking_consistency(
    comparisons: List[RankingComparisonResult],
) -> Optional[float]:
    """Fraction of tier comparisons where higher tier outperforms."""
    if not comparisons:
        return None
    effective = sum(1 for c in comparisons if c.is_effective)
    return round(effective / len(comparisons), 4)
