# -*- coding: utf-8 -*-
"""
TDD tests for Phase 2d: EntryStrategyDEnhanced — 60-minute precise entry.

Strategy D Enhanced adds:
1. Multi-timeframe alignment (daily + 60min)
2. 60min MACD bullish divergence as entry confirmation
3. Enhanced scoring incorporating alignment and divergence
"""

import unittest
from unittest.mock import patch, MagicMock

import numpy as np
import pandas as pd


def _make_daily_df(n: int = 150, trend: str = "up") -> pd.DataFrame:
    np.random.seed(42)
    if trend == "up":
        prices = np.linspace(10, 25, n) + np.random.randn(n) * 0.1
    else:
        prices = np.linspace(25, 10, n) + np.random.randn(n) * 0.1
    vol = np.random.randint(100000, 500000, n).astype(float)
    return pd.DataFrame({
        "date": pd.date_range(end="2025-12-31", periods=n, freq="B"),
        "open": prices - 0.1,
        "high": prices + 0.2,
        "low": prices - 0.2,
        "close": prices,
        "volume": vol,
    })


def _make_60min_df(n: int = 200, trend: str = "up") -> pd.DataFrame:
    np.random.seed(43)
    if trend == "up":
        prices = np.linspace(23, 26, n) + np.random.randn(n) * 0.05
    else:
        prices = np.linspace(26, 22, n) + np.random.randn(n) * 0.05
    return pd.DataFrame({
        "datetime": pd.date_range(start="2025-12-15 09:30", periods=n, freq="60min"),
        "open": prices - 0.02,
        "high": prices + 0.05,
        "low": prices - 0.05,
        "close": prices,
        "volume": np.random.randint(10000, 100000, n),
    })


class TestEntryStrategyDEnhancedImport(unittest.TestCase):
    def test_import(self):
        from src.strategies.entry_strategies import EntryStrategyDEnhanced
        self.assertIsNotNone(EntryStrategyDEnhanced)


class TestDailyOnlyFallback(unittest.TestCase):
    """Without intraday data, behaves like original EntryStrategyD."""

    def test_daily_only_returns_result(self):
        from src.strategies.entry_strategies import EntryStrategyDEnhanced
        daily_df = _make_daily_df(trend="up")
        result = EntryStrategyDEnhanced.evaluate(daily_df=daily_df, intraday_df=None)
        self.assertIn("triggered", result)
        self.assertIn("alignment_score", result)
        self.assertIn("entry_timing", result)

    def test_daily_only_no_intraday_boost(self):
        from src.strategies.entry_strategies import EntryStrategyDEnhanced
        daily_df = _make_daily_df(trend="up")
        result = EntryStrategyDEnhanced.evaluate(daily_df=daily_df, intraday_df=None)
        self.assertFalse(result.get("intraday_macd_bull_divergence", False))


class TestEnhancedWithIntraday(unittest.TestCase):
    """With 60min data, should produce alignment and divergence info."""

    def test_has_alignment_score(self):
        from src.strategies.entry_strategies import EntryStrategyDEnhanced
        daily_df = _make_daily_df(trend="up")
        intra_df = _make_60min_df(trend="up")
        result = EntryStrategyDEnhanced.evaluate(
            daily_df=daily_df, intraday_df=intra_df
        )
        self.assertIn("alignment_score", result)
        self.assertIsInstance(result["alignment_score"], (int, float))

    def test_has_entry_timing(self):
        from src.strategies.entry_strategies import EntryStrategyDEnhanced
        daily_df = _make_daily_df(trend="up")
        intra_df = _make_60min_df(trend="up")
        result = EntryStrategyDEnhanced.evaluate(
            daily_df=daily_df, intraday_df=intra_df
        )
        self.assertIn(result["entry_timing"], ("strong", "moderate", "weak", "none"))

    def test_aligned_up_scores_higher(self):
        from src.strategies.entry_strategies import EntryStrategyDEnhanced
        daily_up = _make_daily_df(trend="up")
        intra_up = _make_60min_df(trend="up")
        r1 = EntryStrategyDEnhanced.evaluate(daily_df=daily_up, intraday_df=intra_up)

        daily_up2 = _make_daily_df(trend="up")
        intra_down = _make_60min_df(trend="down")
        r2 = EntryStrategyDEnhanced.evaluate(daily_df=daily_up2, intraday_df=intra_down)

        self.assertGreaterEqual(r1["score"], r2["score"])


class TestInsufficientData(unittest.TestCase):
    def test_short_daily(self):
        from src.strategies.entry_strategies import EntryStrategyDEnhanced
        short_df = _make_daily_df(n=10, trend="up")
        result = EntryStrategyDEnhanced.evaluate(daily_df=short_df, intraday_df=None)
        self.assertFalse(result["triggered"])

    def test_short_intraday_ignored(self):
        from src.strategies.entry_strategies import EntryStrategyDEnhanced
        daily_df = _make_daily_df(trend="up")
        short_intra = _make_60min_df(n=5, trend="up")
        result = EntryStrategyDEnhanced.evaluate(
            daily_df=daily_df, intraday_df=short_intra
        )
        self.assertIsNone(result.get("intraday_trend"))


if __name__ == "__main__":
    unittest.main()
