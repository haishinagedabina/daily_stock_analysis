# -*- coding: utf-8 -*-
"""
TDD tests for Phase 3d: EntryStrategyDEnhanced with trendline confirmation.

Adds trendline_breakout_boost to EntryStrategyDEnhanced:
- If daily trendline breakout (upward), score bonus + confirmation flag
- trendline_confirmed field in result
"""

import unittest
import numpy as np
import pandas as pd


def _make_daily_breakout(n: int = 150) -> pd.DataFrame:
    """Daily data with a downtrend followed by a breakout."""
    prices = np.zeros(n)
    prices[:80] = np.linspace(25, 15, 80)
    prices[80:120] = np.linspace(15, 14, 40)
    prices[120:150] = np.linspace(14, 24, 30)
    noise = np.random.RandomState(42).randn(n) * 0.1
    prices = prices + noise
    vol = np.random.RandomState(42).randint(100000, 500000, n).astype(float)
    return pd.DataFrame({
        "date": pd.date_range(end="2025-12-31", periods=n, freq="B"),
        "open": prices - 0.1,
        "high": prices + 0.2,
        "low": prices - 0.2,
        "close": prices,
        "volume": vol,
    })


def _make_60min_up(n: int = 200) -> pd.DataFrame:
    np.random.seed(43)
    prices = np.linspace(22, 25, n) + np.random.randn(n) * 0.05
    return pd.DataFrame({
        "datetime": pd.date_range(start="2025-12-15 09:30", periods=n, freq="60min"),
        "open": prices - 0.02,
        "high": prices + 0.05,
        "low": prices - 0.05,
        "close": prices,
        "volume": np.random.randint(10000, 100000, n),
    })


class TestTrendlineConfirmationField(unittest.TestCase):
    """EntryStrategyDEnhanced result contains trendline_confirmed."""

    def test_field_exists(self):
        from src.strategies.entry_strategies import EntryStrategyDEnhanced
        daily = _make_daily_breakout()
        intra = _make_60min_up()
        result = EntryStrategyDEnhanced.evaluate(daily_df=daily, intraday_df=intra)
        self.assertIn("trendline_confirmed", result)
        self.assertIsInstance(result["trendline_confirmed"], bool)

    def test_field_exists_without_intraday(self):
        from src.strategies.entry_strategies import EntryStrategyDEnhanced
        daily = _make_daily_breakout()
        result = EntryStrategyDEnhanced.evaluate(daily_df=daily, intraday_df=None)
        self.assertIn("trendline_confirmed", result)

    def test_field_false_on_short_data(self):
        from src.strategies.entry_strategies import EntryStrategyDEnhanced
        short = pd.DataFrame({
            "date": pd.date_range(end="2025-12-31", periods=10, freq="B"),
            "open": [10]*10, "high": [10.5]*10, "low": [9.5]*10,
            "close": [10]*10, "volume": [100000]*10,
        })
        result = EntryStrategyDEnhanced.evaluate(daily_df=short, intraday_df=None)
        self.assertFalse(result["trendline_confirmed"])


if __name__ == "__main__":
    unittest.main()
