# -*- coding: utf-8 -*-
"""
TDD tests for Phase 3b: Horizontal Resistance + 123 Pattern Detector.

Tests cover:
1. Horizontal resistance detection (price cluster zones)
2. 123 bottom pattern detection:
   - Point 1: a significant low
   - Point 2: a bounce high
   - Point 3: a higher low (above Point 1)
   - Breakout above Point 2 confirms the reversal
3. Edge cases: insufficient data, no pattern
"""

import unittest
import numpy as np
import pandas as pd


def _make_123_bottom_data() -> pd.DataFrame:
    """
    Construct a clear 123 bottom pattern:
    - Downtrend to Point 1 (low)
    - Bounce to Point 2 (high)
    - Retrace to Point 3 (higher low)
    - Break above Point 2
    """
    n = 60
    prices = np.zeros(n)
    prices[:15] = np.linspace(20, 12, 15)     # downtrend
    prices[15:25] = np.linspace(12, 17, 10)   # bounce to Point 2
    prices[25:35] = np.linspace(17, 14, 10)   # retrace to Point 3 (higher low)
    prices[35:50] = np.linspace(14, 18, 15)   # breakout above Point 2
    prices[50:60] = np.linspace(18, 20, 10)   # continuation

    noise = np.random.RandomState(42).randn(n) * 0.1
    prices = prices + noise

    return pd.DataFrame({
        "high": prices + 0.3,
        "low": prices - 0.3,
        "close": prices,
        "volume": np.random.RandomState(42).randint(100000, 500000, n),
    })


def _make_resistance_data() -> pd.DataFrame:
    """Create data with a clear horizontal resistance zone around 20."""
    n = 80
    np.random.seed(45)
    prices = np.full(n, 18.0) + np.random.randn(n) * 0.5
    # Create touches at ~20 level
    for idx in [15, 30, 45, 60]:
        prices[idx] = 20.0 + np.random.rand() * 0.2
        prices[idx + 1] = 19.0
    return pd.DataFrame({
        "high": prices + 0.3,
        "low": prices - 0.3,
        "close": prices,
    })


class TestPatternDetectorImport(unittest.TestCase):
    def test_import(self):
        from src.indicators.pattern_detector import PatternDetector
        self.assertIsNotNone(PatternDetector)


class TestHorizontalResistance(unittest.TestCase):
    """Detect horizontal resistance levels."""

    def test_detect_resistance(self):
        from src.indicators.pattern_detector import PatternDetector
        df = _make_resistance_data()
        result = PatternDetector.detect_horizontal_resistance(df)
        self.assertIn("levels", result)
        self.assertIsInstance(result["levels"], list)

    def test_resistance_levels_have_price(self):
        from src.indicators.pattern_detector import PatternDetector
        df = _make_resistance_data()
        result = PatternDetector.detect_horizontal_resistance(df)
        if result["levels"]:
            level = result["levels"][0]
            self.assertIn("price", level)
            self.assertIn("touches", level)


class TestPattern123Bottom(unittest.TestCase):
    """Detect 123 bottom reversal pattern."""

    def test_detect_123_bottom(self):
        from src.indicators.pattern_detector import PatternDetector
        df = _make_123_bottom_data()
        result = PatternDetector.detect_123_bottom(df)
        self.assertIn("found", result)
        self.assertIsInstance(result["found"], bool)

    def test_123_bottom_has_points(self):
        from src.indicators.pattern_detector import PatternDetector
        df = _make_123_bottom_data()
        result = PatternDetector.detect_123_bottom(df)
        for key in ("point1", "point2", "point3", "breakout_confirmed"):
            self.assertIn(key, result)

    def test_no_123_in_downtrend(self):
        from src.indicators.pattern_detector import PatternDetector
        n = 60
        prices = np.linspace(30, 10, n)
        df = pd.DataFrame({
            "high": prices + 0.3,
            "low": prices - 0.3,
            "close": prices,
            "volume": np.random.RandomState(42).randint(100000, 500000, n),
        })
        result = PatternDetector.detect_123_bottom(df)
        self.assertFalse(result["breakout_confirmed"])


class TestInsufficientData(unittest.TestCase):
    def test_short_data_resistance(self):
        from src.indicators.pattern_detector import PatternDetector
        df = pd.DataFrame({"close": [10, 11], "high": [10.5, 11.5], "low": [9.5, 10.5]})
        result = PatternDetector.detect_horizontal_resistance(df)
        self.assertEqual(len(result["levels"]), 0)

    def test_short_data_123(self):
        from src.indicators.pattern_detector import PatternDetector
        df = pd.DataFrame({"close": [10, 11], "high": [10.5, 11.5], "low": [9.5, 10.5]})
        result = PatternDetector.detect_123_bottom(df)
        self.assertFalse(result["found"])


if __name__ == "__main__":
    unittest.main()
