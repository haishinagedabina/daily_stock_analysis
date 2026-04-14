# -*- coding: utf-8 -*-
"""TDD RED phase: Tests for EntrySignalEvaluator.

Computes forward returns, MAE/MFE, drawdown, signal quality score.
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
class TestEntrySignalEvaluator(unittest.TestCase):

    def _evaluate(self, entry_price, forward_bars, take_profit_pct=None,
                  stop_loss_pct=None):
        from src.backtest.evaluators.entry_evaluator import EntrySignalEvaluator
        return EntrySignalEvaluator.evaluate(
            entry_price=entry_price,
            forward_bars=forward_bars,
            take_profit_pct=take_profit_pct,
            stop_loss_pct=stop_loss_pct,
        )

    def test_forward_returns_basic(self):
        """Should compute 1d, 3d, 5d, 10d forward returns."""
        bars = [MockBar(date(2024, 1, d), 100+d, 102+d, 99+d, 101+d) for d in range(1, 12)]
        result = self._evaluate(100.0, bars)
        # 1d return = (close[0] - entry) / entry * 100
        self.assertIsNotNone(result.forward_return_1d)
        self.assertIsNotNone(result.forward_return_3d)
        self.assertIsNotNone(result.forward_return_5d)
        self.assertIsNotNone(result.forward_return_10d)

    def test_forward_return_1d_correct(self):
        """1-day return should be (close_day1 - entry) / entry * 100."""
        bars = [MockBar(date(2024, 1, 16), 101.0, 105.0, 99.0, 103.0)]
        result = self._evaluate(100.0, bars)
        self.assertAlmostEqual(result.forward_return_1d, 3.0)

    def test_mae_correct(self):
        """MAE = max adverse excursion (worst drawdown from entry)."""
        bars = [
            MockBar(date(2024, 1, 16), 100.0, 105.0, 95.0, 102.0),  # low=95
            MockBar(date(2024, 1, 17), 102.0, 108.0, 97.0, 106.0),  # low=97
        ]
        result = self._evaluate(100.0, bars)
        # MAE = (95 - 100) / 100 * 100 = -5.0
        self.assertAlmostEqual(result.mae, -5.0)

    def test_mfe_correct(self):
        """MFE = max favorable excursion (best runup from entry)."""
        bars = [
            MockBar(date(2024, 1, 16), 100.0, 105.0, 95.0, 102.0),  # high=105
            MockBar(date(2024, 1, 17), 102.0, 108.0, 97.0, 106.0),  # high=108
        ]
        result = self._evaluate(100.0, bars)
        # MFE = (108 - 100) / 100 * 100 = 8.0
        self.assertAlmostEqual(result.mfe, 8.0)

    def test_max_drawdown_from_peak(self):
        """Peak-to-trough drawdown during holding period."""
        bars = [
            MockBar(date(2024, 1, 16), 100.0, 110.0, 100.0, 108.0),  # peak=110
            MockBar(date(2024, 1, 17), 108.0, 109.0, 95.0, 96.0),    # trough=95
        ]
        result = self._evaluate(100.0, bars)
        # drawdown = (95 - 110) / 110 * 100 = -13.64%
        self.assertAlmostEqual(result.max_drawdown_from_peak, -13.64, places=1)

    def test_signal_quality_score(self):
        """signal_quality_score = MFE / (MFE + |MAE|), range 0-1."""
        bars = [
            MockBar(date(2024, 1, 16), 100.0, 106.0, 97.0, 104.0),
        ]
        result = self._evaluate(100.0, bars)
        # MFE=6.0, MAE=-3.0 → score = 6/(6+3) = 0.667
        expected = 6.0 / (6.0 + 3.0)
        self.assertAlmostEqual(result.signal_quality_score, expected, places=2)

    def test_plan_success_take_profit_hit(self):
        """plan_success=True when take-profit is hit."""
        bars = [
            MockBar(date(2024, 1, 16), 100.0, 100.5, 99.5, 100.0),
            MockBar(date(2024, 1, 17), 100.0, 106.0, 99.0, 105.0),
        ]
        result = self._evaluate(100.0, bars, take_profit_pct=5.0, stop_loss_pct=-3.0)
        self.assertTrue(result.plan_success)

    def test_plan_success_stop_loss_hit(self):
        """plan_success=False when stop-loss is hit first."""
        bars = [
            MockBar(date(2024, 1, 16), 100.0, 100.5, 99.5, 100.0),
            MockBar(date(2024, 1, 17), 100.0, 101.0, 96.0, 97.0),
        ]
        result = self._evaluate(100.0, bars, take_profit_pct=5.0, stop_loss_pct=-3.0)
        self.assertFalse(result.plan_success)

    def test_empty_bars(self):
        """Should return empty result for no bars."""
        result = self._evaluate(100.0, [])
        self.assertIsNone(result.forward_return_1d)

    def test_holding_days(self):
        """Should track holding period length."""
        bars = [MockBar(date(2024, 1, d), 100.0, 105.0, 95.0, 100.0) for d in range(16, 26)]
        result = self._evaluate(100.0, bars)
        self.assertEqual(result.holding_days, 10)


if __name__ == "__main__":
    unittest.main()
