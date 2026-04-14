# -*- coding: utf-8 -*-
"""ExitSignalEvaluator: framework only, PRODUCTION_READY=False.

Will be activated when exit-type sample source is sufficient.
"""
from __future__ import annotations

from typing import Any, List, Optional

from src.backtest.evaluators.base_evaluator import BaseEvaluator, EvaluationResult


class ExitSignalEvaluator(BaseEvaluator):
    """Framework exit evaluator — returns empty results."""

    PRODUCTION_READY = False

    @staticmethod
    def evaluate(
        entry_price: Optional[float] = None,
        exit_price: Optional[float] = None,
        forward_bars: Optional[List[Any]] = None,
        **kwargs,
    ) -> EvaluationResult:
        return EvaluationResult()
