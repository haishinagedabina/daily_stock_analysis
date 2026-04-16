# -*- coding: utf-8 -*-
"""Evidence builder for backtest recommendations.

Constructs traceable evidence JSON linking a recommendation back to
the group summary, evaluation samples, and threshold checks that
support it.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from src.backtest.aggregators.sample_threshold import SampleThresholdGate, ThresholdResult
from src.backtest.models.backtest_models import (
    FiveLayerBacktestEvaluation,
    FiveLayerBacktestGroupSummary,
)
from src.backtest.utils.summary_metrics import get_sample_baseline


class EvidenceBuilder:
    """Builds traceable evidence chains for recommendations.

    Every recommendation must carry an evidence_json that allows
    auditors to trace back to:
      - The group summary it was derived from
      - A sample of evaluation IDs supporting the claim
      - The threshold check result
      - Key metric snapshot at time of recommendation
    """

    @staticmethod
    def build(
        group_summary: FiveLayerBacktestGroupSummary,
        evaluations_sample: List[FiveLayerBacktestEvaluation],
        threshold_result: ThresholdResult,
        extra: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Build evidence JSON string.

        Args:
            group_summary: The summary this recommendation is based on.
            evaluations_sample: Representative evaluation records (up to 10).
            threshold_result: Result of sample threshold check.
            extra: Additional context to include.

        Returns:
            JSON string with full evidence chain.
        """
        evidence: Dict[str, Any] = {
            "source_summary": {
                "group_type": group_summary.group_type,
                "group_key": group_summary.group_key,
                "sample_count": group_summary.sample_count,
                "sample_baseline": get_sample_baseline(group_summary),
                "avg_return_pct": group_summary.avg_return_pct,
                "median_return_pct": group_summary.median_return_pct,
                "win_rate_pct": group_summary.win_rate_pct,
                "p25_return_pct": group_summary.p25_return_pct,
                "p75_return_pct": group_summary.p75_return_pct,
                "extreme_sample_ratio": group_summary.extreme_sample_ratio,
                "time_bucket_stability": group_summary.time_bucket_stability,
            },
            "threshold_check": {
                "sample_count": threshold_result.sample_count,
                "can_display": threshold_result.can_display,
                "can_suggest": threshold_result.can_suggest,
                "can_action": threshold_result.can_action,
                "reason": threshold_result.reason,
            },
            "sample_evaluation_ids": [
                e.id for e in evaluations_sample[:10] if e.id is not None
            ],
            "sample_codes": [
                e.code for e in evaluations_sample[:10] if e.code is not None
            ],
        }

        if extra:
            evidence["extra"] = extra

        return json.dumps(evidence, ensure_ascii=False)
