# -*- coding: utf-8 -*-
"""Five-layer backtest recommendations package.

Provides the recommendation engine and evidence builder for generating
graded, traceable suggestions from backtest results.

RED LINE: This package ONLY outputs suggestions. It NEVER modifies
production rules, thresholds, or parameters.
"""
from src.backtest.recommendations.evidence_builder import EvidenceBuilder
from src.backtest.recommendations.recommendation_engine import RecommendationEngine

__all__ = [
    "EvidenceBuilder",
    "RecommendationEngine",
]
