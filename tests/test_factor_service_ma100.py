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


if __name__ == "__main__":
    unittest.main()
