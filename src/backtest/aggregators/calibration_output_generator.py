# -*- coding: utf-8 -*-
"""Calibration output generator for five-layer backtest.

Compares baseline vs candidate config summaries, computes delta metrics,
and produces a decision (accept / reject / inconclusive) with confidence.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from src.backtest.models.backtest_models import (
    FiveLayerBacktestCalibrationOutput,
    FiveLayerBacktestGroupSummary,
)

logger = logging.getLogger(__name__)

# ── Decision thresholds ─────────────────────────────────────────────────────

_ACCEPT_IMPROVEMENT_PCT = 5.0    # candidate must improve main metric by >= 5%
_REJECT_DEGRADATION_PCT = -3.0   # candidate degrades main metric by >= 3%
_MIN_CONFIDENCE = 0.3            # below this → inconclusive


@dataclass(frozen=True)
class CalibrationDelta:
    """Delta between baseline and candidate metrics."""

    metric_name: str
    baseline_value: Optional[float]
    candidate_value: Optional[float]
    delta: Optional[float]
    delta_pct: Optional[float]


class CalibrationOutputGenerator:
    """Generates calibration comparison outputs.

    Compares overall summaries from a baseline run and a candidate run,
    computes deltas across key metrics, and renders a decision.
    """

    @staticmethod
    def generate(
        backtest_run_id: str,
        calibration_name: str,
        baseline_summary: FiveLayerBacktestGroupSummary,
        candidate_summary: FiveLayerBacktestGroupSummary,
        baseline_config: Dict[str, Any],
        candidate_config: Dict[str, Any],
    ) -> FiveLayerBacktestCalibrationOutput:
        """Generate a calibration output comparing baseline vs candidate.

        Args:
            backtest_run_id: The run that owns this calibration.
            calibration_name: Human-readable experiment label.
            baseline_summary: Overall summary from baseline run.
            candidate_summary: Overall summary from candidate run.
            baseline_config: Config dict used for baseline run.
            candidate_config: Config dict used for candidate run.

        Returns:
            A fully populated CalibrationOutput (not yet persisted).
        """
        deltas = _compute_deltas(baseline_summary, candidate_summary)
        decision, confidence = _decide(deltas, baseline_summary, candidate_summary)

        delta_dict = {
            d.metric_name: {
                "baseline": d.baseline_value,
                "candidate": d.candidate_value,
                "delta": d.delta,
                "delta_pct": d.delta_pct,
            }
            for d in deltas
        }

        return FiveLayerBacktestCalibrationOutput(
            backtest_run_id=backtest_run_id,
            calibration_name=calibration_name,
            baseline_config_json=json.dumps(baseline_config, ensure_ascii=False),
            candidate_config_json=json.dumps(candidate_config, ensure_ascii=False),
            delta_metrics_json=json.dumps(delta_dict, ensure_ascii=False),
            decision=decision,
            confidence=round(confidence, 4),
            created_at=datetime.now(),
        )


# ── Internal helpers ────────────────────────────────────────────────────────

_COMPARISON_METRICS = [
    ("avg_return_pct", True),      # higher is better
    ("median_return_pct", True),
    ("win_rate_pct", True),
    ("avg_mae", False),            # lower (less negative) is better
    ("avg_mfe", True),
    ("avg_drawdown", False),       # lower (less negative) is better
]


def _compute_deltas(
    baseline: FiveLayerBacktestGroupSummary,
    candidate: FiveLayerBacktestGroupSummary,
) -> List[CalibrationDelta]:
    """Compute deltas for each comparison metric."""
    results: List[CalibrationDelta] = []
    for metric_name, _ in _COMPARISON_METRICS:
        b_val = getattr(baseline, metric_name, None)
        c_val = getattr(candidate, metric_name, None)
        delta = None
        delta_pct = None
        if b_val is not None and c_val is not None:
            delta = round(c_val - b_val, 4)
            if b_val != 0:
                delta_pct = round((c_val - b_val) / abs(b_val) * 100, 4)
        results.append(CalibrationDelta(
            metric_name=metric_name,
            baseline_value=b_val,
            candidate_value=c_val,
            delta=delta,
            delta_pct=delta_pct,
        ))
    return results


def _decide(
    deltas: List[CalibrationDelta],
    baseline: FiveLayerBacktestGroupSummary,
    candidate: FiveLayerBacktestGroupSummary,
) -> Tuple[str, float]:
    """Produce decision and confidence from deltas.

    Logic:
      - Primary metric: avg_return_pct delta_pct
      - If improvement >= _ACCEPT_IMPROVEMENT_PCT → accept
      - If degradation <= _REJECT_DEGRADATION_PCT → reject
      - Otherwise → inconclusive
      - Confidence = weighted count of metrics that improve / total
    """
    # Primary decision based on avg_return_pct
    primary = next((d for d in deltas if d.metric_name == "avg_return_pct"), None)

    if primary is None or primary.delta_pct is None:
        return "inconclusive", 0.0

    # Count improvements considering direction preference
    metric_dir = {name: higher_better for name, higher_better in _COMPARISON_METRICS}
    improvement_count = 0
    total_with_data = 0

    for d in deltas:
        if d.delta is None:
            continue
        total_with_data += 1
        higher_better = metric_dir.get(d.metric_name, True)
        if higher_better and d.delta > 0:
            improvement_count += 1
        elif not higher_better and d.delta < 0:
            improvement_count += 1

    confidence = improvement_count / total_with_data if total_with_data > 0 else 0.0

    if confidence < _MIN_CONFIDENCE:
        return "inconclusive", confidence

    if primary.delta_pct >= _ACCEPT_IMPROVEMENT_PCT:
        return "accept", confidence
    elif primary.delta_pct <= _REJECT_DEGRADATION_PCT:
        return "reject", confidence

    return "inconclusive", confidence
