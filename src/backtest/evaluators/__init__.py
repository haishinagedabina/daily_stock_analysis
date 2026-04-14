# -*- coding: utf-8 -*-
"""Five-layer backtest evaluators.

Three signal families, each with its own evaluator:
  - EntrySignalEvaluator: forward returns, MAE/MFE, signal quality
  - ObservationSignalEvaluator: counterfactual risk/opportunity
  - ExitSignalEvaluator: framework only (PRODUCTION_READY=False)
"""
from src.backtest.evaluators.base_evaluator import BaseEvaluator, EvaluationResult  # noqa: F401
from src.backtest.evaluators.entry_evaluator import EntrySignalEvaluator  # noqa: F401
from src.backtest.evaluators.exit_evaluator import ExitSignalEvaluator  # noqa: F401
from src.backtest.evaluators.observation_evaluator import ObservationSignalEvaluator  # noqa: F401

__all__ = [
    "BaseEvaluator",
    "EntrySignalEvaluator",
    "EvaluationResult",
    "ExitSignalEvaluator",
    "ObservationSignalEvaluator",
]
