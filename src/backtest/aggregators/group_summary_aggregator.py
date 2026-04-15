# -*- coding: utf-8 -*-
"""Group summary aggregator for five-layer backtest evaluations.

Computes overall, single-dimension, and combo group summaries from
the candidate-level evaluation fact table. Uses snapshot fields
(not replayed) for historical_snapshot mode grouping.
"""
from __future__ import annotations

import json
import logging
import statistics
from collections import defaultdict
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from src.backtest.aggregators.sample_threshold import SampleThresholdGate, ThresholdResult
from src.backtest.aggregators.stability_metrics import StabilityMetricsCalculator
from src.backtest.models.backtest_models import (
    FiveLayerBacktestEvaluation,
    FiveLayerBacktestGroupSummary,
)
from src.backtest.repositories.evaluation_repo import EvaluationRepository
from src.backtest.repositories.summary_repo import SummaryRepository

logger = logging.getLogger(__name__)

# ── Grouping dimensions ─────────────────────────────────────────────────────

SINGLE_DIMENSIONS = (
    "signal_family",
    "snapshot_setup_type",
    "snapshot_market_regime",
    "snapshot_theme_position",
    "snapshot_candidate_pool_level",
    "snapshot_entry_maturity",
    "snapshot_trade_stage",
)

COMBO_PAIRS: List[Tuple[str, str]] = [
    ("snapshot_theme_position", "snapshot_setup_type"),
    ("snapshot_candidate_pool_level", "snapshot_entry_maturity"),
    ("snapshot_market_regime", "signal_family"),
]

# Map field name → group_type label
_DIMENSION_TO_GROUP_TYPE = {
    "signal_family": "signal_family",
    "snapshot_setup_type": "setup_type",
    "snapshot_market_regime": "market_regime",
    "snapshot_theme_position": "theme_position",
    "snapshot_candidate_pool_level": "candidate_pool_level",
    "snapshot_entry_maturity": "entry_maturity",
    "snapshot_trade_stage": "trade_stage",
}


class GroupSummaryAggregator:
    """Computes and persists group summaries for a backtest run.

    Produces three kinds of summaries:
      1. overall  — single row aggregating all evaluations
      2. single-dimension — one row per unique value of each dimension
      3. combo — one row per unique (dim_a, dim_b) pair
    """

    def __init__(
        self,
        eval_repo: Optional[EvaluationRepository] = None,
        summary_repo: Optional[SummaryRepository] = None,
    ):
        self.eval_repo = eval_repo or EvaluationRepository()
        self.summary_repo = summary_repo or SummaryRepository()

    def compute_all_summaries(
        self,
        backtest_run_id: str,
    ) -> List[FiveLayerBacktestGroupSummary]:
        """Compute and persist all group summaries for a run.

        Returns list of all persisted summary records.
        """
        evaluations = self.eval_repo.get_by_run(backtest_run_id)
        if not evaluations:
            logger.warning("No evaluations found for run %s", backtest_run_id)
            return []

        results: List[FiveLayerBacktestGroupSummary] = []

        # 1. Overall summary
        overall = self._persist_group(
            backtest_run_id, "overall", "all", evaluations,
        )
        if overall:
            results.append(overall)

        # 2. Single-dimension summaries
        for dim in SINGLE_DIMENSIONS:
            group_type = _DIMENSION_TO_GROUP_TYPE.get(dim, dim)
            grouped = _group_by_field(evaluations, dim)
            for group_key, evals in grouped.items():
                summary = self._persist_group(
                    backtest_run_id, group_type, group_key, evals,
                )
                if summary:
                    results.append(summary)

        # 3. Combo summaries
        for dim_a, dim_b in COMBO_PAIRS:
            group_type = "combo"
            grouped = _group_by_combo(evaluations, dim_a, dim_b)
            for group_key, evals in grouped.items():
                summary = self._persist_group(
                    backtest_run_id, group_type, group_key, evals,
                )
                if summary:
                    results.append(summary)

        logger.info(
            "Computed %d summaries for run %s", len(results), backtest_run_id,
        )
        return results

    def _persist_group(
        self,
        backtest_run_id: str,
        group_type: str,
        group_key: str,
        evaluations: List[FiveLayerBacktestEvaluation],
    ) -> Optional[FiveLayerBacktestGroupSummary]:
        """Aggregate a group of evaluations and persist to DB.

        Always persists the summary. Threshold info is stored as advisory
        metadata in metrics_json — gating is the RecommendationEngine's job.
        """
        metrics = aggregate_group(evaluations)
        if metrics is None:
            return None

        threshold = SampleThresholdGate.check(metrics["sample_count"])

        # Store threshold info in metrics_json (advisory, not a gate)
        extra = {
            "threshold_check": {
                "can_display": threshold.can_display,
                "can_suggest": threshold.can_suggest,
                "can_action": threshold.can_action,
                "reason": threshold.reason,
            },
        }

        return self.summary_repo.upsert_summary(
            backtest_run_id=backtest_run_id,
            group_type=group_type,
            group_key=group_key,
            sample_count=metrics["sample_count"],
            avg_return_pct=metrics["avg_return_pct"],
            median_return_pct=metrics["median_return_pct"],
            win_rate_pct=metrics["win_rate_pct"],
            avg_mae=metrics["avg_mae"],
            avg_mfe=metrics["avg_mfe"],
            avg_drawdown=metrics["avg_drawdown"],
            p25_return_pct=metrics["p25_return_pct"],
            p75_return_pct=metrics["p75_return_pct"],
            extreme_sample_ratio=metrics["extreme_sample_ratio"],
            time_bucket_stability=metrics["time_bucket_stability"],
            profit_factor=metrics["profit_factor"],
            avg_holding_days=metrics["avg_holding_days"],
            max_consecutive_losses=metrics["max_consecutive_losses"],
            plan_execution_rate=metrics["plan_execution_rate"],
            stage_accuracy_rate=metrics["stage_accuracy_rate"],
            metrics_json=json.dumps(extra, ensure_ascii=False),
            computed_at=datetime.now(),
        )


# ── Pure aggregation functions ──────────────────────────────────────────────

def aggregate_group(
    evaluations: List[FiveLayerBacktestEvaluation],
) -> Optional[Dict[str, Any]]:
    """Compute aggregate metrics for a group of evaluations.

    Uses forward_return_5d as the primary return metric.
    Returns None if no valid evaluations.
    """
    # Filter to evaluated entries with a return metric
    valid = [
        e for e in evaluations
        if e.forward_return_5d is not None or e.risk_avoided_pct is not None
    ]
    if not valid:
        return None

    n = len(valid)

    # Primary return: forward_return_5d for entry, risk_avoided_pct for observation
    returns = []
    for e in valid:
        if e.forward_return_5d is not None:
            returns.append(e.forward_return_5d)
        elif e.risk_avoided_pct is not None:
            returns.append(e.risk_avoided_pct)

    if not returns:
        return None

    # Trade dates for stability
    trade_dates = [e.trade_date for e in valid if e.trade_date is not None]

    # Win rate: "win" for entry, "correct_wait" for observation
    _WIN_OUTCOMES = frozenset({"win", "correct_wait"})
    win_count = sum(1 for e in valid if e.outcome in _WIN_OUTCOMES)
    win_rate = (win_count / n) * 100 if n > 0 else 0.0

    # MAE / MFE / Drawdown
    mae_vals = [e.mae for e in valid if e.mae is not None]
    mfe_vals = [e.mfe for e in valid if e.mfe is not None]
    dd_vals = [e.max_drawdown_from_peak for e in valid if e.max_drawdown_from_peak is not None]
    holding_vals = [
        e.holding_days for e in valid
        if e.holding_days is not None and e.holding_days > 0
    ]

    # Stability metrics
    stability = StabilityMetricsCalculator.compute(returns, trade_dates)

    positive_returns = [r for r in returns if r > 0]
    negative_returns = [r for r in returns if r < 0]
    total_positive = sum(positive_returns) if positive_returns else 0
    total_negative = abs(sum(negative_returns)) if negative_returns else 0
    profit_factor = round(total_positive / total_negative, 4) if total_negative > 0 else None

    sorted_evals = sorted(
        [e for e in valid if e.trade_date is not None and e.outcome is not None],
        key=lambda e: (e.trade_date, e.code),
    )
    max_consecutive_losses = 0
    current_streak = 0
    for evaluation in sorted_evals:
        if evaluation.outcome == "loss":
            current_streak += 1
            max_consecutive_losses = max(max_consecutive_losses, current_streak)
            continue
        current_streak = 0

    plan_evals = [e for e in valid if e.plan_success is not None]
    plan_execution_rate = (
        round(sum(1 for e in plan_evals if e.plan_success) / len(plan_evals), 4)
        if plan_evals else None
    )

    stage_correct = 0
    stage_total = 0
    for evaluation in valid:
        if evaluation.signal_family == "entry" and evaluation.forward_return_5d is not None:
            stage_total += 1
            if evaluation.forward_return_5d > 0:
                stage_correct += 1
        elif evaluation.signal_family == "observation" and evaluation.stage_success is not None:
            stage_total += 1
            if evaluation.stage_success:
                stage_correct += 1

    return {
        "sample_count": n,
        "avg_return_pct": round(statistics.mean(returns), 4) if returns else None,
        "median_return_pct": stability.median,
        "win_rate_pct": round(win_rate, 2),
        "avg_mae": round(statistics.mean(mae_vals), 4) if mae_vals else None,
        "avg_mfe": round(statistics.mean(mfe_vals), 4) if mfe_vals else None,
        "avg_drawdown": round(statistics.mean(dd_vals), 4) if dd_vals else None,
        "p25_return_pct": stability.p25,
        "p75_return_pct": stability.p75,
        "extreme_sample_ratio": stability.extreme_sample_ratio,
        "time_bucket_stability": stability.time_bucket_stability,
        "profit_factor": profit_factor,
        "avg_holding_days": round(statistics.mean(holding_vals), 2) if holding_vals else None,
        "max_consecutive_losses": max_consecutive_losses,
        "plan_execution_rate": plan_execution_rate,
        "stage_accuracy_rate": round(stage_correct / stage_total, 4) if stage_total > 0 else None,
    }


def _group_by_field(
    evaluations: List[FiveLayerBacktestEvaluation],
    field: str,
) -> Dict[str, List[FiveLayerBacktestEvaluation]]:
    """Group evaluations by a single snapshot field value."""
    groups: Dict[str, List[FiveLayerBacktestEvaluation]] = defaultdict(list)
    for e in evaluations:
        val = getattr(e, field, None)
        if val is not None:
            groups[str(val)].append(e)
    return dict(groups)


def _group_by_combo(
    evaluations: List[FiveLayerBacktestEvaluation],
    field_a: str,
    field_b: str,
) -> Dict[str, List[FiveLayerBacktestEvaluation]]:
    """Group evaluations by a combination of two snapshot fields."""
    groups: Dict[str, List[FiveLayerBacktestEvaluation]] = defaultdict(list)
    for e in evaluations:
        val_a = getattr(e, field_a, None)
        val_b = getattr(e, field_b, None)
        if val_a is not None and val_b is not None:
            combo_key = f"{val_a}+{val_b}"
            groups[combo_key].append(e)
    return dict(groups)
