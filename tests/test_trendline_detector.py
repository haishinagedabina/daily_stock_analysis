# -*- coding: utf-8 -*-
"""
TDD tests for Phase 3a: Trendline Detector.

Tests cover:
1. Uptrend line detection (connect swing lows)
2. Downtrend line detection (connect swing highs)
3. Trendline breakout detection
4. Trendline slope and intercept
5. Edge cases: insufficient data, flat data
"""

import unittest
import numpy as np
import pandas as pd


def _make_uptrend_data(n: int = 80) -> pd.DataFrame:
    """Create data with a clear uptrend (higher lows)."""
    np.random.seed(42)
    base = np.linspace(10, 25, n)
    noise = np.random.randn(n) * 0.3
    cycle = np.sin(np.linspace(0, 6 * np.pi, n)) * 1.5
    prices = base + noise + cycle
    return pd.DataFrame({
        "high": prices + 0.5,
        "low": prices - 0.5,
        "close": prices,
    })


def _make_downtrend_data(n: int = 80) -> pd.DataFrame:
    """Create data with a clear downtrend (lower highs)."""
    np.random.seed(43)
    base = np.linspace(25, 10, n)
    noise = np.random.randn(n) * 0.3
    cycle = np.sin(np.linspace(0, 6 * np.pi, n)) * 1.5
    prices = base + noise + cycle
    return pd.DataFrame({
        "high": prices + 0.5,
        "low": prices - 0.5,
        "close": prices,
    })


def _make_breakout_data() -> pd.DataFrame:
    """Create data where price breaks above a downtrend line near the end."""
    n = 80
    base = np.linspace(25, 15, n)
    noise = np.random.RandomState(44).randn(n) * 0.2
    cycle = np.sin(np.linspace(0, 5 * np.pi, n)) * 1.0
    prices = base + noise + cycle
    # Force a breakout in the last few bars
    prices[-5:] = np.linspace(16, 22, 5)
    return pd.DataFrame({
        "high": prices + 0.3,
        "low": prices - 0.3,
        "close": prices,
    })


class TestTrendlineDetectorImport(unittest.TestCase):
    def test_import(self):
        from src.indicators.trendline_detector import TrendlineDetector
        self.assertIsNotNone(TrendlineDetector)


class TestUptrendLine(unittest.TestCase):
    """Detect uptrend support line from swing lows."""

    def test_detect_uptrend(self):
        from src.indicators.trendline_detector import TrendlineDetector
        df = _make_uptrend_data()
        result = TrendlineDetector.detect_uptrend(df)
        self.assertIn("found", result)
        self.assertIn("slope", result)
        self.assertIn("intercept", result)
        self.assertIn("touch_count", result)

    def test_uptrend_slope_positive(self):
        from src.indicators.trendline_detector import TrendlineDetector
        df = _make_uptrend_data()
        result = TrendlineDetector.detect_uptrend(df)
        if result["found"]:
            self.assertGreater(result["slope"], 0)


class TestDowntrendLine(unittest.TestCase):
    """Detect downtrend resistance line from swing highs."""

    def test_detect_downtrend(self):
        from src.indicators.trendline_detector import TrendlineDetector
        df = _make_downtrend_data()
        result = TrendlineDetector.detect_downtrend(df)
        self.assertIn("found", result)
        self.assertIn("slope", result)
        self.assertIn("intercept", result)

    def test_downtrend_slope_negative(self):
        from src.indicators.trendline_detector import TrendlineDetector
        df = _make_downtrend_data()
        result = TrendlineDetector.detect_downtrend(df)
        if result["found"]:
            self.assertLess(result["slope"], 0)


class TestTrendlineBreakout(unittest.TestCase):
    """Detect breakout above downtrend resistance."""

    def test_detect_breakout(self):
        from src.indicators.trendline_detector import TrendlineDetector
        df = _make_breakout_data()
        result = TrendlineDetector.detect_trendline_breakout(df)
        self.assertIn("breakout", result)
        self.assertIsInstance(result["breakout"], bool)

    def test_breakout_has_direction(self):
        from src.indicators.trendline_detector import TrendlineDetector
        df = _make_breakout_data()
        result = TrendlineDetector.detect_trendline_breakout(df)
        self.assertIn("direction", result)


class TestInsufficientData(unittest.TestCase):
    def test_short_data_uptrend(self):
        from src.indicators.trendline_detector import TrendlineDetector
        df = pd.DataFrame({"close": [10, 11], "high": [10.5, 11.5], "low": [9.5, 10.5]})
        result = TrendlineDetector.detect_uptrend(df)
        self.assertFalse(result["found"])

    def test_short_data_downtrend(self):
        from src.indicators.trendline_detector import TrendlineDetector
        df = pd.DataFrame({"close": [10, 11], "high": [10.5, 11.5], "low": [9.5, 10.5]})
        result = TrendlineDetector.detect_downtrend(df)
        self.assertFalse(result["found"])


if __name__ == "__main__":
    unittest.main()
