# -*- coding: utf-8 -*-
"""Base evaluator ABC and EvaluationResult dataclass."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, List, Optional


@dataclass
class EvaluationResult:
    """Unified result container for all evaluator types."""
    # Forward returns
    forward_return_1d: Optional[float] = None
    forward_return_3d: Optional[float] = None
    forward_return_5d: Optional[float] = None
    forward_return_10d: Optional[float] = None

    # Risk metrics
    mae: Optional[float] = None
    mfe: Optional[float] = None
    max_drawdown_from_peak: Optional[float] = None
    holding_days: int = 0

    # Plan outcome
    plan_success: Optional[bool] = None
    signal_quality_score: Optional[float] = None

    # Observation-specific
    risk_avoided_pct: Optional[float] = None
    opportunity_cost_pct: Optional[float] = None
    stage_success: Optional[bool] = None
    would_have_hit_stop: Optional[bool] = None
    would_have_hit_profit: Optional[bool] = None

    # Outcome label
    outcome: Optional[str] = None


class BaseEvaluator(ABC):
    """Abstract base for signal evaluators."""

    PRODUCTION_READY: bool = True

    @staticmethod
    @abstractmethod
    def evaluate(**kwargs) -> EvaluationResult:
        ...
