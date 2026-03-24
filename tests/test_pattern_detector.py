# -*- coding: utf-8 -*-
"""
TDD tests for Phase 3b: Horizontal Resistance + 123 Pattern Detector.

Tests cover:
1. Horizontal resistance detection (price cluster zones)
2. 123 bottom pattern detection — correctness of:
   a. Newest-first search (returns the most-recent valid pattern)
   b. Stale breakout rejection (breakout must be within breakout_window)
   c. Swing detection near the right edge (asymmetric window)
   d. No false positive on pure downtrend
3. Edge cases: insufficient data, no pattern
"""

import unittest
import numpy as np
import pandas as pd


def _make_ohlcv(prices: np.ndarray, seed: int = 42) -> pd.DataFrame:
    rng = np.random.RandomState(seed)
    spread = 0.3
    vol = rng.randint(100_000, 500_000, len(prices)).astype(float)
    return pd.DataFrame({
        "high":   prices + spread,
        "low":    prices - spread,
        "close":  prices,
        "volume": vol,
    })


def _make_123_bottom_data() -> pd.DataFrame:
    """
    Clear 123 bottom: downtrend → P1 → bounce → P2 → retrace → P3 → breakout.
    Pattern is centred in the middle of a 60-bar series.
    """
    n = 60
    prices = np.zeros(n)
    prices[:15]  = np.linspace(20, 12, 15)   # downtrend to P1
    prices[15:25] = np.linspace(12, 17, 10)  # bounce to P2
    prices[25:35] = np.linspace(17, 14, 10)  # retrace to P3
    prices[35:50] = np.linspace(14, 18, 15)  # breakout above P2
    prices[50:60] = np.linspace(18, 20, 10)  # continuation
    noise = np.random.RandomState(42).randn(n) * 0.1
    return _make_ohlcv(prices + noise)


def _make_two_123_patterns() -> pd.DataFrame:
    """
    Two consecutive 123 bottoms; the second (newer) pattern should be
    returned when the algorithm is correct.
    """
    n = 120
    prices = np.zeros(n)
    # First (old) pattern — bars 0-59
    prices[:15]  = np.linspace(20, 12, 15)
    prices[15:25] = np.linspace(12, 17, 10)
    prices[25:35] = np.linspace(17, 14, 10)
    prices[35:50] = np.linspace(14, 19, 15)
    prices[50:60] = np.linspace(19, 22, 10)
    # Second (recent) pattern — bars 60-119
    prices[60:75]  = np.linspace(22, 16, 15)
    prices[75:85]  = np.linspace(16, 21, 10)
    prices[85:95]  = np.linspace(21, 18, 10)
    prices[95:110] = np.linspace(18, 23, 15)
    prices[110:120] = np.linspace(23, 25, 10)
    noise = np.random.RandomState(7).randn(n) * 0.1
    return _make_ohlcv(prices + noise)


def _make_stale_breakout_data() -> pd.DataFrame:
    """
    123 pattern whose breakout happened > 15 bars ago so should NOT be
    confirmed under the breakout_window constraint.
    """
    n = 100
    prices = np.zeros(n)
    prices[:15]  = np.linspace(20, 12, 15)
    prices[15:25] = np.linspace(12, 17, 10)
    prices[25:35] = np.linspace(17, 14, 10)
    # Breakout at bars 35-50 (50 bars before end)
    prices[35:50] = np.linspace(14, 20, 15)
    # Then price drifts sideways / back — no fresh breakout
    prices[50:100] = 19.0
    noise = np.random.RandomState(3).randn(n) * 0.05
    return _make_ohlcv(prices + noise)


def _make_resistance_data() -> pd.DataFrame:
    """Create data with a clear horizontal resistance zone around 20."""
    n = 80
    np.random.seed(45)
    prices = np.full(n, 18.0) + np.random.randn(n) * 0.5
    for idx in [15, 30, 45, 60]:
        prices[idx]     = 20.0 + np.random.rand() * 0.2
        prices[idx + 1] = 19.0
    return pd.DataFrame({
        "high":  prices + 0.3,
        "low":   prices - 0.3,
        "close": prices,
    })


# ---------------------------------------------------------------------------
# Import smoke tests
# ---------------------------------------------------------------------------

class TestPatternDetectorImport(unittest.TestCase):
    def test_import(self):
        from src.indicators.pattern_detector import PatternDetector
        self.assertIsNotNone(PatternDetector)


# ---------------------------------------------------------------------------
# Horizontal resistance
# ---------------------------------------------------------------------------

class TestHorizontalResistance(unittest.TestCase):

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


# ---------------------------------------------------------------------------
# 123 bottom — basic structure
# ---------------------------------------------------------------------------

class TestPattern123Bottom(unittest.TestCase):

    def test_detect_123_bottom_found(self):
        from src.indicators.pattern_detector import PatternDetector
        df = _make_123_bottom_data()
        result = PatternDetector.detect_123_bottom(df)
        self.assertTrue(result["found"], "should detect a 123 bottom in clean data")

    def test_123_bottom_has_all_keys(self):
        from src.indicators.pattern_detector import PatternDetector
        df = _make_123_bottom_data()
        result = PatternDetector.detect_123_bottom(df)
        for key in ("point1", "point2", "point3", "breakout_confirmed",
                    "bars_since_p3", "bars_since_breakout"):
            self.assertIn(key, result)

    def test_123_bottom_point_order(self):
        """P1 < P2 < P3 in time; P3.low > P1.low; P2.high > P1.low."""
        from src.indicators.pattern_detector import PatternDetector
        df = _make_123_bottom_data()
        result = PatternDetector.detect_123_bottom(df)
        if not result["found"]:
            self.skipTest("pattern not found — skip structural check")
        p1, p2, p3 = result["point1"], result["point2"], result["point3"]
        self.assertLess(p1["idx"], p2["idx"])
        self.assertLess(p2["idx"], p3["idx"])
        self.assertGreater(p3["price"], p1["price"])
        self.assertGreater(p2["price"], p1["price"])

    def test_breakout_confirmed_in_clean_pattern(self):
        from src.indicators.pattern_detector import PatternDetector
        df = _make_123_bottom_data()
        result = PatternDetector.detect_123_bottom(df)
        self.assertTrue(result.get("breakout_confirmed"),
                        "breakout should be confirmed in clean pattern data")

    def test_no_123_in_downtrend(self):
        from src.indicators.pattern_detector import PatternDetector
        n = 60
        prices = np.linspace(30, 10, n)
        df = _make_ohlcv(prices)
        result = PatternDetector.detect_123_bottom(df)
        self.assertFalse(result["breakout_confirmed"])


# ---------------------------------------------------------------------------
# Newest-first: two patterns → most-recent returned
# ---------------------------------------------------------------------------

class TestPattern123NewestFirst(unittest.TestCase):

    def test_returns_most_recent_pattern(self):
        """When two valid 123 patterns exist the later one must be returned."""
        from src.indicators.pattern_detector import PatternDetector
        df = _make_two_123_patterns()
        result = PatternDetector.detect_123_bottom(df, lookback=80)
        self.assertTrue(result["found"])
        # The second pattern's P1 is around bar 60-75 — idx must be ≥ 60
        p1_idx = result["point1"]["idx"]
        self.assertGreaterEqual(
            p1_idx, 55,
            f"Expected P1 in the second (newer) pattern (idx≥55), got idx={p1_idx}",
        )


# ---------------------------------------------------------------------------
# Stale breakout rejection
# ---------------------------------------------------------------------------

class TestPattern123StaleBreakout(unittest.TestCase):

    def test_stale_breakout_not_confirmed(self):
        """A breakout that happened > breakout_window bars ago must not be confirmed."""
        from src.indicators.pattern_detector import PatternDetector
        df = _make_stale_breakout_data()
        # Use a short window so the old breakout at bar ~45 is outside it
        result = PatternDetector.detect_123_bottom(df, breakout_window=10)
        # If the pattern is found, the breakout must NOT be confirmed
        if result["found"]:
            self.assertFalse(
                result["breakout_confirmed"],
                "stale breakout (> breakout_window bars ago) must not be confirmed",
            )

    def test_bars_since_breakout_populated(self):
        """bars_since_breakout must be set when breakout is confirmed."""
        from src.indicators.pattern_detector import PatternDetector
        df = _make_123_bottom_data()
        result = PatternDetector.detect_123_bottom(df)
        if result.get("breakout_confirmed"):
            self.assertIsNotNone(result["bars_since_breakout"])
            self.assertGreaterEqual(result["bars_since_breakout"], 0)


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

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
