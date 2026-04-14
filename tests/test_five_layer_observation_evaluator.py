# -*- coding: utf-8 -*-
"""TDD RED phase: Tests for ObservationSignalEvaluator.

Counterfactual: risk_avoided vs opportunity_cost for non-entry signals.
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
class TestObservationSignalEvaluator(unittest.TestCase):

    def _evaluate(self, hypothetical_entry_price, forward_bars):
        from src.backtest.evaluators.observation_evaluator import ObservationSignalEvaluator
        return ObservationSignalEvaluator.evaluate(
            hypothetical_entry_price=hypothetical_entry_price,
            forward_bars=forward_bars,
        )

    def test_risk_avoided_pct(self):
        """risk_avoided = max drawdown of hypothetical entry."""
        bars = [
            MockBar(date(2024, 1, 16), 100.0, 102.0, 92.0, 95.0),  # low=92 → -8%
        ]
        result = self._evaluate(100.0, bars)
        # risk_avoided = |min_low - entry| / entry * 100 = 8.0
        self.assertAlmostEqual(result.risk_avoided_pct, 8.0)

    def test_opportunity_cost_pct(self):
        """opportunity_cost = max upside missed."""
        bars = [
            MockBar(date(2024, 1, 16), 100.0, 112.0, 99.0, 110.0),  # high=112 → +12%
        ]
        result = self._evaluate(100.0, bars)
        self.assertAlmostEqual(result.opportunity_cost_pct, 12.0)

    def test_stage_success_waiting_was_right(self):
        """stage_success=True if risk_avoided > opportunity_cost (waiting was right)."""
        bars = [
            MockBar(date(2024, 1, 16), 100.0, 103.0, 88.0, 90.0),  # risk=12%, opp=3%
        ]
        result = self._evaluate(100.0, bars)
        self.assertTrue(result.stage_success)

    def test_stage_success_should_have_entered(self):
        """stage_success=False if opportunity_cost > risk_avoided."""
        bars = [
            MockBar(date(2024, 1, 16), 100.0, 115.0, 99.0, 112.0),  # risk=1%, opp=15%
        ]
        result = self._evaluate(100.0, bars)
        self.assertFalse(result.stage_success)

    def test_would_have_hit_stop(self):
        """would_have_hit_stop=True when drawdown exceeds typical 3% stop."""
        bars = [
            MockBar(date(2024, 1, 16), 100.0, 101.0, 95.0, 96.0),  # -5% > -3%
        ]
        result = self._evaluate(100.0, bars)
        self.assertTrue(result.would_have_hit_stop)

    def test_would_have_hit_profit(self):
        """would_have_hit_profit=True when upside exceeds typical 5% target."""
        bars = [
            MockBar(date(2024, 1, 16), 100.0, 107.0, 99.0, 106.0),  # +7% > +5%
        ]
        result = self._evaluate(100.0, bars)
        self.assertTrue(result.would_have_hit_profit)

    def test_empty_bars(self):
        """Should return empty result for no bars."""
        result = self._evaluate(100.0, [])
        self.assertIsNone(result.risk_avoided_pct)

    def test_multiple_bars_uses_extremes(self):
        """Should use min low and max high across all bars."""
        bars = [
            MockBar(date(2024, 1, 16), 100.0, 105.0, 98.0, 103.0),
            MockBar(date(2024, 1, 17), 103.0, 110.0, 96.0, 108.0),
            MockBar(date(2024, 1, 18), 108.0, 108.0, 90.0, 92.0),
        ]
        result = self._evaluate(100.0, bars)
        # risk_avoided = (100-90)/100*100 = 10.0
        # opportunity_cost = (110-100)/100*100 = 10.0
        self.assertAlmostEqual(result.risk_avoided_pct, 10.0)
        self.assertAlmostEqual(result.opportunity_cost_pct, 10.0)


if __name__ == "__main__":
    unittest.main()
