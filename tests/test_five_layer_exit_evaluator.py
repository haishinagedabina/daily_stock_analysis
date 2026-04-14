# -*- coding: utf-8 -*-
"""TDD RED phase: Tests for ExitSignalEvaluator.

Framework only — PRODUCTION_READY=False. Interface validation.
"""

import unittest
from dataclasses import dataclass
from datetime import date

import pytest


@dataclass
class MockBar:
    date: date
    open: float
    high: float
    low: float
    close: float
    pct_chg: float = 0.0


@pytest.mark.unit
class TestExitSignalEvaluator(unittest.TestCase):

    def test_production_ready_flag_is_false(self):
        """ExitSignalEvaluator.PRODUCTION_READY must be False."""
        from src.backtest.evaluators.exit_evaluator import ExitSignalEvaluator
        self.assertFalse(ExitSignalEvaluator.PRODUCTION_READY)

    def test_evaluate_returns_empty_result(self):
        """Framework evaluator returns empty EvaluationResult."""
        from src.backtest.evaluators.exit_evaluator import ExitSignalEvaluator
        bars = [MockBar(date(2024, 1, 16), 100.0, 105.0, 98.0, 103.0)]
        result = ExitSignalEvaluator.evaluate(
            entry_price=100.0,
            exit_price=103.0,
            forward_bars=bars,
        )
        self.assertIsNotNone(result)
        self.assertIsNone(result.forward_return_1d)

    def test_has_evaluate_method(self):
        """Should expose evaluate() static method."""
        from src.backtest.evaluators.exit_evaluator import ExitSignalEvaluator
        self.assertTrue(callable(getattr(ExitSignalEvaluator, "evaluate", None)))

    def test_inherits_base_evaluator(self):
        """Should inherit from BaseEvaluator."""
        from src.backtest.evaluators.base_evaluator import BaseEvaluator
        from src.backtest.evaluators.exit_evaluator import ExitSignalEvaluator
        self.assertTrue(issubclass(ExitSignalEvaluator, BaseEvaluator))


if __name__ == "__main__":
    unittest.main()
