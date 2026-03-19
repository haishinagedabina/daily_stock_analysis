# -*- coding: utf-8 -*-
"""
TDD tests for Phase 3c: Entry Strategies A and B.

Strategy A: Trendline Breakout
  - Detects downtrend resistance line
  - Price breaks above the trendline
  - Volume confirmation

Strategy B: 123 Bottom Reversal
  - Detects 123 bottom pattern
  - Breakout above Point 2 confirmed
  - Above MA100 filter (optional)
"""

import unittest
import numpy as np
import pandas as pd


def _make_trendline_breakout_data(n: int = 100) -> pd.DataFrame:
    """Create data with a downtrend followed by a breakout."""
    prices = np.zeros(n)
    prices[:60] = np.linspace(30, 18, 60)
    prices[60:80] = np.linspace(18, 16, 20)
    prices[80:100] = np.linspace(16, 25, 20)  # strong breakout
    noise = np.random.RandomState(42).randn(n) * 0.1
    prices = prices + noise
    vol = np.random.RandomState(42).randint(100000, 500000, n).astype(float)
    vol[-5:] = vol[-5:] * 2  # volume surge at breakout
    return pd.DataFrame({
        "high": prices + 0.3,
        "low": prices - 0.3,
        "close": prices,
        "volume": vol,
        "pct_chg": np.diff(prices, prepend=prices[0]) / np.maximum(np.abs(prices), 0.01) * 100,
    })


def _make_123_bottom_entry_data(n: int = 100) -> pd.DataFrame:
    """Create data with a 123 bottom pattern."""
    prices = np.zeros(n)
    prices[:20] = np.linspace(25, 12, 20)     # downtrend
    prices[20:35] = np.linspace(12, 18, 15)   # bounce (P2)
    prices[35:50] = np.linspace(18, 14, 15)   # retrace (P3 higher low)
    prices[50:70] = np.linspace(14, 20, 20)   # breakout above P2
    prices[70:100] = np.linspace(20, 22, 30)  # continuation

    noise = np.random.RandomState(42).randn(n) * 0.1
    prices = prices + noise
    vol = np.random.RandomState(42).randint(100000, 500000, n).astype(float)

    return pd.DataFrame({
        "high": prices + 0.3,
        "low": prices - 0.3,
        "close": prices,
        "volume": vol,
        "pct_chg": np.diff(prices, prepend=prices[0]) / np.maximum(np.abs(prices), 0.01) * 100,
    })


class TestEntryStrategyAImport(unittest.TestCase):
    def test_import(self):
        from src.strategies.entry_strategies import EntryStrategyA
        self.assertIsNotNone(EntryStrategyA)


class TestEntryStrategyA(unittest.TestCase):
    """Trendline breakout strategy."""

    def test_returns_result(self):
        from src.strategies.entry_strategies import EntryStrategyA
        df = _make_trendline_breakout_data()
        result = EntryStrategyA.evaluate(df)
        self.assertIn("triggered", result)
        self.assertIn("score", result)
        self.assertIn("trendline_breakout", result)

    def test_insufficient_data(self):
        from src.strategies.entry_strategies import EntryStrategyA
        short_df = pd.DataFrame({
            "close": [10, 11], "high": [10.5, 11.5], "low": [9.5, 10.5],
            "volume": [100000, 100000],
        })
        result = EntryStrategyA.evaluate(short_df)
        self.assertFalse(result["triggered"])

    def test_score_range(self):
        from src.strategies.entry_strategies import EntryStrategyA
        df = _make_trendline_breakout_data()
        result = EntryStrategyA.evaluate(df)
        self.assertGreaterEqual(result["score"], 0)
        self.assertLessEqual(result["score"], 100)


class TestEntryStrategyBImport(unittest.TestCase):
    def test_import(self):
        from src.strategies.entry_strategies import EntryStrategyB
        self.assertIsNotNone(EntryStrategyB)


class TestEntryStrategyB(unittest.TestCase):
    """123 bottom reversal strategy."""

    def test_returns_result(self):
        from src.strategies.entry_strategies import EntryStrategyB
        df = _make_123_bottom_entry_data()
        result = EntryStrategyB.evaluate(df)
        self.assertIn("triggered", result)
        self.assertIn("score", result)
        self.assertIn("pattern_123", result)

    def test_insufficient_data(self):
        from src.strategies.entry_strategies import EntryStrategyB
        short_df = pd.DataFrame({
            "close": [10, 11], "high": [10.5, 11.5], "low": [9.5, 10.5],
            "volume": [100000, 100000],
        })
        result = EntryStrategyB.evaluate(short_df)
        self.assertFalse(result["triggered"])

    def test_score_range(self):
        from src.strategies.entry_strategies import EntryStrategyB
        df = _make_123_bottom_entry_data()
        result = EntryStrategyB.evaluate(df)
        self.assertGreaterEqual(result["score"], 0)
        self.assertLessEqual(result["score"], 100)


if __name__ == "__main__":
    unittest.main()
