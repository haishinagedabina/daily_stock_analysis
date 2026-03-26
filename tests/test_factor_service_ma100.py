# -*- coding: utf-8 -*-
"""
TDD tests for Phase 1f: FactorService MA100 factor extension.

Tests verify that _compute_extended_factors and helper methods produce
the new MA100 and gap/limit-up factors correctly.
"""

import unittest
import numpy as np
import pandas as pd

from src.services.factor_service import FactorService


def _make_group(n: int = 120, base: float = 10.0, trend: float = 0.002) -> pd.DataFrame:
    """Generate a stock group DataFrame mimicking DB rows."""
    np.random.seed(42)
    prices = [base]
    for _ in range(n - 1):
        change = np.random.randn() * 0.01 + trend
        prices.append(prices[-1] * (1 + change))
    close = np.array(prices)
    dates = pd.date_range(start="2025-01-01", periods=n, freq="D")
    return pd.DataFrame({
        "date": dates,
        "open": close * 0.999,
        "high": close * (1 + np.random.uniform(0, 0.015, n)),
        "low": close * (1 - np.random.uniform(0, 0.015, n)),
        "close": close,
        "volume": np.random.randint(1_000_000, 5_000_000, n),
        "pct_chg": np.concatenate([[0], np.diff(close) / close[:-1] * 100]),
    })


class TestComputeMA100Factors(unittest.TestCase):

    def test_returns_ma100_fields(self):
        group = _make_group(n=120)
        close_series = group["close"].astype(float)
        result = FactorService._compute_ma100_factors(group, close_series, float(close_series.iloc[-1]))
        self.assertIn("ma100", result)
        self.assertIn("above_ma100", result)
        self.assertIn("ma100_distance_pct", result)
        self.assertIn("ma100_breakout_days", result)
        self.assertIn("pullback_ma100", result)
        self.assertIn("pullback_ma20", result)
        self.assertIn("stop_loss_price", result)
        self.assertIn("stop_loss_ma", result)

    def test_ma100_positive_in_uptrend(self):
        group = _make_group(n=120, trend=0.003)
        close_series = group["close"].astype(float)
        result = FactorService._compute_ma100_factors(group, close_series, float(close_series.iloc[-1]))
        self.assertGreater(result["ma100"], 0)
        self.assertTrue(result["above_ma100"])

    def test_ma100_zero_when_insufficient(self):
        group = _make_group(n=50)
        close_series = group["close"].astype(float)
        result = FactorService._compute_ma100_factors(group, close_series, float(close_series.iloc[-1]))
        self.assertEqual(result["ma100"], 0.0)


class TestComputeGapLimitFactors(unittest.TestCase):

    def test_returns_gap_limit_fields(self):
        group = _make_group(n=60)
        result = FactorService._compute_gap_limit_factors(group)
        self.assertIn("gap_up", result)
        self.assertIn("gap_breakaway", result)
        self.assertIn("is_limit_up", result)
        self.assertIn("limit_up_breakout", result)

    def test_no_gap_in_normal_data(self):
        group = _make_group(n=60)
        result = FactorService._compute_gap_limit_factors(group)
        self.assertFalse(result["gap_breakaway"])


class TestExtendedFactorsIntegration(unittest.TestCase):

    def test_extended_factors_include_ma100(self):
        fs = FactorService.__new__(FactorService)
        group = _make_group(n=120)
        latest = group.iloc[-1]
        close_series = group["close"].astype(float)
        result = fs._compute_extended_factors(group, latest, close_series)
        self.assertIn("ma100", result)
        self.assertIn("above_ma100", result)
        self.assertIn("gap_up", result)
        self.assertIn("is_limit_up", result)
        # Original factors still present
        self.assertIn("pct_chg_5d", result)
        self.assertIn("candle_pattern", result)

    def test_extended_factors_include_ma100_60min(self):
        fs = FactorService.__new__(FactorService)
        group = _make_group(n=120)
        latest = group.iloc[-1]
        close_series = group["close"].astype(float)
        result = fs._compute_extended_factors(group, latest, close_series)
        self.assertIn("ma100_60min_confirmed", result)
        self.assertIn("ma100_60min_freshness_score", result)
        self.assertIn("ma100_60min_ma_score", result)
        self.assertIn("ma100_60min_hit_reasons", result)


class TestMA10060minCombinedFactors(unittest.TestCase):

    def test_confirmed_when_fresh_breakout(self):
        ma100_factors = {
            "above_ma100": True,
            "ma100_breakout_days": 3,
            "ma100": 50.0,
            "ma100_distance_pct": 2.0,
        }
        result = FactorService._compute_ma100_60min_combined_factors(ma100_factors)
        self.assertTrue(result["ma100_60min_confirmed"])
        self.assertGreater(result["ma100_60min_freshness_score"], 0)
        self.assertGreater(result["ma100_60min_ma_score"], 0)

    def test_rejected_when_stale_breakout(self):
        ma100_factors = {
            "above_ma100": True,
            "ma100_breakout_days": 8,
            "ma100": 50.0,
            "ma100_distance_pct": 2.0,
        }
        result = FactorService._compute_ma100_60min_combined_factors(ma100_factors)
        self.assertFalse(result["ma100_60min_confirmed"])
        self.assertEqual(result["ma100_60min_freshness_score"], 0.0)

    def test_rejected_when_below_ma100(self):
        ma100_factors = {
            "above_ma100": False,
            "ma100_breakout_days": 2,
            "ma100": 50.0,
            "ma100_distance_pct": -3.0,
        }
        result = FactorService._compute_ma100_60min_combined_factors(ma100_factors)
        self.assertFalse(result["ma100_60min_confirmed"])

    def test_rejected_when_breakout_days_zero(self):
        """breakout_days=0 means not yet broken out — should reject."""
        ma100_factors = {
            "above_ma100": True,
            "ma100_breakout_days": 0,
            "ma100": 50.0,
            "ma100_distance_pct": 1.0,
        }
        result = FactorService._compute_ma100_60min_combined_factors(ma100_factors)
        self.assertFalse(result["ma100_60min_confirmed"])

    def test_hit_reasons_include_60min_guidance(self):
        ma100_factors = {
            "above_ma100": True,
            "ma100_breakout_days": 2,
            "ma100": 48.50,
            "ma100_distance_pct": 3.1,
        }
        result = FactorService._compute_ma100_60min_combined_factors(ma100_factors)
        reasons = result["ma100_60min_hit_reasons"]
        self.assertEqual(len(reasons), 2)
        self.assertIn("MA100站稳确认", reasons[0])
        self.assertIn("60分钟入场提示", reasons[1])
        self.assertIn("48.50", reasons[1])

    def test_freshness_score_decreases_with_days(self):
        scores = []
        for days in [1, 3, 5]:
            ma100_factors = {
                "above_ma100": True,
                "ma100_breakout_days": days,
                "ma100": 50.0,
                "ma100_distance_pct": 2.0,
            }
            result = FactorService._compute_ma100_60min_combined_factors(ma100_factors)
            scores.append(result["ma100_60min_freshness_score"])
        # 1d > 3d > 5d
        self.assertGreater(scores[0], scores[1])
        self.assertGreater(scores[1], scores[2])
        # exact values: 1d=1.0, 3d=0.8, 5d=0.6
        self.assertAlmostEqual(scores[0], 1.0)
        self.assertAlmostEqual(scores[1], 0.8)
        self.assertAlmostEqual(scores[2], 0.6)


if __name__ == "__main__":
    unittest.main()
