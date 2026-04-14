# -*- coding: utf-8 -*-
"""Recommendation engine for five-layer backtest.

RED LINE: This engine ONLY outputs structured suggestions.
It NEVER modifies production rules, thresholds, classification
mappings, or execution parameters. All 'actionable' recommendations
still require human review or independent replay/calibration
verification before entering any rule-change workflow.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

from src.backtest.aggregators.sample_threshold import (
    ACTIONABLE_MIN,
    OBSERVATION_MIN,
    SUGGESTION_MIN,
    SampleThresholdGate,
    ThresholdResult,
)
from src.backtest.models.backtest_models import (
    FiveLayerBacktestGroupSummary,
    FiveLayerBacktestRecommendation,
)
from src.backtest.recommendations.evidence_builder import EvidenceBuilder
from src.backtest.repositories.evaluation_repo import EvaluationRepository
from src.backtest.repositories.recommendation_repo import RecommendationRepository
from src.backtest.repositories.summary_repo import SummaryRepository

logger = logging.getLogger(__name__)

# ── Gate thresholds ─────────────────────────────────────────────────────────

TIME_BUCKET_STABILITY_MAX = 0.15   # max stddev of bucket win rates
EXTREME_SAMPLE_RATIO_MAX = 0.10    # max fraction of extreme outliers
WIN_RATE_STRONG_THRESHOLD = 60.0   # win_rate above this = strong signal
WIN_RATE_WEAK_THRESHOLD = 40.0     # win_rate below this = weak signal


@dataclass
class RecommendationDraft:
    """Internal draft before gate checks."""

    group_summary: FiveLayerBacktestGroupSummary
    recommendation_type: str
    target_scope: str
    target_key: str
    current_rule: str
    suggested_change: str
    threshold_result: ThresholdResult
    stability_passed: bool
    consistency_passed: bool


class RecommendationEngine:
    """Generates graded recommendations from backtest summaries.

    IMPORTANT — Permission boundary:
      This engine ONLY produces structured suggestions stored in
      five_layer_backtest_recommendations. It has NO write access
      to production config, rules, thresholds, or parameters.

    Grading:
      observation  — sample >= 5, no stability requirement
      hypothesis   — sample >= 20, stability check passed
      actionable   — sample >= 50, stability + consistency + evidence
    """

    def __init__(
        self,
        summary_repo: Optional[SummaryRepository] = None,
        eval_repo: Optional[EvaluationRepository] = None,
        recommendation_repo: Optional[RecommendationRepository] = None,
    ):
        self.summary_repo = summary_repo or SummaryRepository()
        self.eval_repo = eval_repo or EvaluationRepository()
        self.recommendation_repo = recommendation_repo or RecommendationRepository()

    def generate_recommendations(
        self,
        backtest_run_id: str,
    ) -> List[FiveLayerBacktestRecommendation]:
        """Generate all recommendations for a completed run.

        ONLY outputs suggestions. NEVER modifies rules/thresholds/parameters.

        Steps:
          1. Load all group summaries (excluding 'overall')
          2. For each group, evaluate whether a recommendation is warranted
          3. Apply gates to determine recommendation level
          4. Build evidence chain
          5. Persist and return
        """
        summaries = self.summary_repo.get_by_run(backtest_run_id)
        if not summaries:
            logger.info("No summaries for run %s, skipping recommendations", backtest_run_id)
            return []

        recommendations: List[FiveLayerBacktestRecommendation] = []

        for summary in summaries:
            if summary.group_type == "overall":
                continue

            draft = self._evaluate_group(summary)
            if draft is None:
                continue

            rec = self._build_recommendation(backtest_run_id, draft)
            if rec is not None:
                recommendations.append(rec)

        if recommendations:
            self.recommendation_repo.save_batch(recommendations)
            logger.info(
                "Generated %d recommendations for run %s",
                len(recommendations), backtest_run_id,
            )

        return recommendations

    def _evaluate_group(
        self,
        summary: FiveLayerBacktestGroupSummary,
    ) -> Optional[RecommendationDraft]:
        """Evaluate a single group summary for recommendation potential."""
        threshold = SampleThresholdGate.check(summary.sample_count or 0)
        if not threshold.can_display:
            return None

        # Determine recommendation type based on group performance
        rec_type, current_rule, suggested_change = _infer_recommendation(summary)
        if rec_type is None:
            return None

        # Stability check
        stability_passed = _check_stability(summary)

        # Consistency check: win_rate and avg_return agree on direction
        consistency_passed = _check_consistency(summary)

        return RecommendationDraft(
            group_summary=summary,
            recommendation_type=rec_type,
            target_scope=summary.group_type,
            target_key=summary.group_key,
            current_rule=current_rule,
            suggested_change=suggested_change,
            threshold_result=threshold,
            stability_passed=stability_passed,
            consistency_passed=consistency_passed,
        )

    def _build_recommendation(
        self,
        backtest_run_id: str,
        draft: RecommendationDraft,
    ) -> Optional[FiveLayerBacktestRecommendation]:
        """Apply gates and build final recommendation record."""
        level = _determine_level(
            draft.threshold_result,
            draft.stability_passed,
            draft.consistency_passed,
        )
        if level is None:
            return None

        # Build evidence from evaluation samples
        evaluations = self.eval_repo.get_by_run(backtest_run_id)
        field_map = _group_type_to_field(draft.target_scope)
        sample_evals = [
            e for e in evaluations
            if field_map and getattr(e, field_map, None) == draft.target_key
        ][:10]

        evidence_json = EvidenceBuilder.build(
            group_summary=draft.group_summary,
            evaluations_sample=sample_evals,
            threshold_result=draft.threshold_result,
        )

        confidence = _compute_confidence(draft)

        summary = draft.group_summary
        metrics_snapshot = {
            "avg_return_pct": summary.avg_return_pct,
            "win_rate_pct": summary.win_rate_pct,
            "median_return_pct": summary.median_return_pct,
            "sample_count": summary.sample_count,
        }

        return FiveLayerBacktestRecommendation(
            backtest_run_id=backtest_run_id,
            recommendation_type=draft.recommendation_type,
            target_scope=draft.target_scope,
            target_key=draft.target_key,
            current_rule=draft.current_rule,
            suggested_change=draft.suggested_change,
            recommendation_level=level,
            sample_count=draft.threshold_result.sample_count,
            confidence=round(confidence, 4),
            validation_status="pending",
            evidence_json=evidence_json,
            metrics_before_json=json.dumps(metrics_snapshot, ensure_ascii=False),
            created_at=datetime.now(),
        )


# ── Pure gate / inference functions ─────────────────────────────────────────

def _determine_level(
    threshold: ThresholdResult,
    stability_passed: bool,
    consistency_passed: bool,
) -> Optional[str]:
    """Determine recommendation level based on gates.

    Returns None if below observation threshold.
    Small samples CANNOT produce actionable — this is a hard red line.
    """
    if not threshold.can_display:
        return None

    if threshold.can_action and stability_passed and consistency_passed:
        return "actionable"
    elif threshold.can_suggest and stability_passed:
        return "hypothesis"
    elif threshold.can_display:
        return "observation"

    return None


def _check_stability(summary: FiveLayerBacktestGroupSummary) -> bool:
    """Check time-bucket stability and extreme sample ratio."""
    tbs = summary.time_bucket_stability
    esr = summary.extreme_sample_ratio

    if tbs is not None and tbs > TIME_BUCKET_STABILITY_MAX:
        return False
    if esr is not None and esr > EXTREME_SAMPLE_RATIO_MAX:
        return False
    return True


def _check_consistency(summary: FiveLayerBacktestGroupSummary) -> bool:
    """Check that win_rate and avg_return agree on direction."""
    wr = summary.win_rate_pct
    ar = summary.avg_return_pct
    if wr is None or ar is None:
        return False

    # Both positive or both negative/weak
    if ar > 0 and wr >= 50:
        return True
    if ar <= 0 and wr < 50:
        return True
    return False


def _infer_recommendation(
    summary: FiveLayerBacktestGroupSummary,
) -> tuple:
    """Infer recommendation type from group summary metrics.

    Returns (recommendation_type, current_rule, suggested_change)
    or (None, None, None) if no recommendation warranted.
    """
    wr = summary.win_rate_pct
    ar = summary.avg_return_pct

    if wr is None or ar is None:
        return None, None, None

    group_desc = f"{summary.group_type}={summary.group_key}"

    if wr >= WIN_RATE_STRONG_THRESHOLD and ar > 0:
        return (
            "weight_increase",
            f"{group_desc}: current weight normal",
            f"Consider increasing weight/priority for {group_desc} "
            f"(win_rate={wr:.1f}%, avg_return={ar:.2f}%)",
        )
    elif wr <= WIN_RATE_WEAK_THRESHOLD and ar < 0:
        return (
            "weight_decrease",
            f"{group_desc}: current weight normal",
            f"Consider decreasing weight/filtering out {group_desc} "
            f"(win_rate={wr:.1f}%, avg_return={ar:.2f}%)",
        )
    elif wr >= 50 and ar < 0:
        return (
            "execution_review",
            f"{group_desc}: win_rate positive but returns negative",
            f"Review execution model for {group_desc} — wins are too small "
            f"or losses too large (win_rate={wr:.1f}%, avg_return={ar:.2f}%)",
        )

    return None, None, None


def _compute_confidence(draft: RecommendationDraft) -> float:
    """Compute confidence score from draft attributes."""
    score = 0.0
    t = draft.threshold_result

    # Sample size contribution (0-0.4)
    if t.can_action:
        score += 0.4
    elif t.can_suggest:
        score += 0.25
    elif t.can_display:
        score += 0.1

    # Stability contribution (0-0.3)
    if draft.stability_passed:
        score += 0.3

    # Consistency contribution (0-0.3)
    if draft.consistency_passed:
        score += 0.3

    return min(score, 1.0)


def _group_type_to_field(group_type: str) -> Optional[str]:
    """Map group_type back to evaluation field name for sample lookup."""
    mapping = {
        "signal_family": "signal_family",
        "setup_type": "snapshot_setup_type",
        "market_regime": "snapshot_market_regime",
        "theme_position": "snapshot_theme_position",
        "candidate_pool_level": "snapshot_candidate_pool_level",
        "entry_maturity": "snapshot_entry_maturity",
        "trade_stage": "snapshot_trade_stage",
    }
    # Handle combo types — use first dimension
    base_type = group_type.split("+")[0] if "+" in group_type else group_type
    return mapping.get(base_type)
