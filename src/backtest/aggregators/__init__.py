# -*- coding: utf-8 -*-
"""Five-layer backtest aggregators package.

Provides group summary computation, ranking effectiveness analysis,
stability metrics, sample threshold gates, and calibration output
generation.
"""
from src.backtest.aggregators.calibration_output_generator import CalibrationOutputGenerator
from src.backtest.aggregators.group_summary_aggregator import GroupSummaryAggregator
from src.backtest.aggregators.ranking_effectiveness import RankingEffectivenessCalculator
from src.backtest.aggregators.sample_threshold import SampleThresholdGate
from src.backtest.aggregators.stability_metrics import StabilityMetricsCalculator

__all__ = [
    "CalibrationOutputGenerator",
    "GroupSummaryAggregator",
    "RankingEffectivenessCalculator",
    "SampleThresholdGate",
    "StabilityMetricsCalculator",
]
