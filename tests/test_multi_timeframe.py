# -*- coding: utf-8 -*-
"""
TDD tests for Phase 2c: Multi-Timeframe Analyzer.

Tests cover:
1. MultiTimeframeAnalyzer initialization
2. Daily-only analysis (no intraday available)
3. Combined daily + 60min analysis
4. Trend alignment scoring
5. MACD divergence check on 60min
6. Entry timing signal
"""

import unittest
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd


def _make_daily_df(n: int = 120, trend: str = "up") -> pd.DataFrame:
    np.random.seed(42)
    if trend == "up":
        prices = np.linspace(10, 25, n) + np.random.randn(n) * 0.2
    elif trend == "down":
        prices = np.linspace(25, 10, n) + np.random.randn(n) * 0.2
    else:
        prices = np.full(n, 15.0) + np.random.randn(n) * 0.3
    return pd.DataFrame({
        "date": pd.date_range(end="2025-12-31", periods=n, freq="B"),
        "open": prices - 0.1,
        "high": prices + 0.2,
        "low": prices - 0.2,
        "close": prices,
        "volume": np.random.randint(100000, 500000, n),
    })


def _make_60min_df(n: int = 200, trend: str = "up") -> pd.DataFrame:
    np.random.seed(43)
    if trend == "up":
        prices = np.linspace(22, 26, n) + np.random.randn(n) * 0.1
    elif trend == "down":
        prices = np.linspace(26, 22, n) + np.random.randn(n) * 0.1
    else:
        prices = np.full(n, 24.0) + np.random.randn(n) * 0.2
    return pd.DataFrame({
        "datetime": pd.date_range(start="2025-12-20 09:30", periods=n, freq="60min"),
        "open": prices - 0.05,
        "high": prices + 0.1,
        "low": prices - 0.1,
        "close": prices,
        "volume": np.random.randint(10000, 100000, n),
    })


class TestMultiTimeframeInit(unittest.TestCase):
    """MultiTimeframeAnalyzer can be instantiated."""

    def test_import_and_create(self):
        from src.indicators.multi_timeframe_analyzer import MultiTimeframeAnalyzer
        analyzer = MultiTimeframeAnalyzer()
        self.assertIsNotNone(analyzer)


class TestDailyOnlyAnalysis(unittest.TestCase):
    """When no intraday data is provided, analyze daily only."""

    def test_daily_only_returns_result(self):
        from src.indicators.multi_timeframe_analyzer import MultiTimeframeAnalyzer
        analyzer = MultiTimeframeAnalyzer()
        daily_df = _make_daily_df(trend="up")
        result = analyzer.analyze(daily_df=daily_df, intraday_df=None)
        self.assertIn("daily_trend", result)
        self.assertIn("alignment_score", result)
        self.assertIn("entry_timing", result)

    def test_daily_only_no_intraday_fields(self):
        from src.indicators.multi_timeframe_analyzer import MultiTimeframeAnalyzer
        analyzer = MultiTimeframeAnalyzer()
        daily_df = _make_daily_df(trend="up")
        result = analyzer.analyze(daily_df=daily_df, intraday_df=None)
        self.assertIsNone(result.get("intraday_trend"))


class TestCombinedAnalysis(unittest.TestCase):
    """Combined daily + 60min analysis."""

    def test_combined_returns_both_trends(self):
        from src.indicators.multi_timeframe_analyzer import MultiTimeframeAnalyzer
        analyzer = MultiTimeframeAnalyzer()
        daily_df = _make_daily_df(trend="up")
        intraday_df = _make_60min_df(trend="up")
        result = analyzer.analyze(daily_df=daily_df, intraday_df=intraday_df)
        self.assertIn("daily_trend", result)
        self.assertIn("intraday_trend", result)

    def test_alignment_score_higher_when_aligned(self):
        from src.indicators.multi_timeframe_analyzer import MultiTimeframeAnalyzer
        analyzer = MultiTimeframeAnalyzer()

        daily_up = _make_daily_df(trend="up")
        intra_up = _make_60min_df(trend="up")
        result_aligned = analyzer.analyze(daily_df=daily_up, intraday_df=intra_up)

        daily_up2 = _make_daily_df(trend="up")
        intra_down = _make_60min_df(trend="down")
        result_conflict = analyzer.analyze(daily_df=daily_up2, intraday_df=intra_down)

        self.assertGreaterEqual(
            result_aligned["alignment_score"],
            result_conflict["alignment_score"],
        )


class TestMACDDivergence60Min(unittest.TestCase):
    """60min MACD divergence is included in combined analysis."""

    def test_macd_divergence_field_present(self):
        from src.indicators.multi_timeframe_analyzer import MultiTimeframeAnalyzer
        analyzer = MultiTimeframeAnalyzer()
        daily_df = _make_daily_df(trend="up")
        intraday_df = _make_60min_df(trend="up")
        result = analyzer.analyze(daily_df=daily_df, intraday_df=intraday_df)
        self.assertIn("intraday_macd_bull_divergence", result)
        self.assertIn("intraday_macd_bear_divergence", result)


class TestEntryTiming(unittest.TestCase):
    """Entry timing signal is computed."""

    def test_entry_timing_present(self):
        from src.indicators.multi_timeframe_analyzer import MultiTimeframeAnalyzer
        analyzer = MultiTimeframeAnalyzer()
        daily_df = _make_daily_df(trend="up")
        intraday_df = _make_60min_df(trend="up")
        result = analyzer.analyze(daily_df=daily_df, intraday_df=intraday_df)
        self.assertIn("entry_timing", result)
        self.assertIn(result["entry_timing"], ("strong", "moderate", "weak", "none"))


class TestInsufficientIntraday(unittest.TestCase):
    """Graceful degradation with too-short intraday data."""

    def test_short_intraday_falls_back(self):
        from src.indicators.multi_timeframe_analyzer import MultiTimeframeAnalyzer
        analyzer = MultiTimeframeAnalyzer()
        daily_df = _make_daily_df(trend="up")
        short_intra = _make_60min_df(n=5, trend="up")
        result = analyzer.analyze(daily_df=daily_df, intraday_df=short_intra)
        self.assertIsNone(result.get("intraday_trend"))


if __name__ == "__main__":
    unittest.main()
