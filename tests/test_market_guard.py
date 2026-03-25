# -*- coding: utf-8 -*-
"""
TDD tests for Phase 1b: MarketGuard - market-level MA100 risk control.

Tests cover:
1. MarketGuard.check() returns MarketGuardResult
2. Market is safe when index is above MA100
3. Market is unsafe when index is below MA100
4. Graceful degradation when data fetch fails
5. Pipeline integration: MarketGuard result is stored
"""

import sys
import types
import unittest
from unittest.mock import patch, MagicMock
from dataclasses import dataclass

import numpy as np
import pandas as pd


def _make_index_df(n: int = 120, base: float = 3000.0, trend: float = 0.001) -> pd.DataFrame:
    """Generate synthetic index daily data."""
    np.random.seed(42)
    prices = [base]
    for _ in range(n - 1):
        change = np.random.randn() * 0.005 + trend
        prices.append(prices[-1] * (1 + change))
    close = np.array(prices)
    dates = pd.date_range(start="2025-01-01", periods=n, freq="D")
    return pd.DataFrame({
        "date": dates,
        "open": close * 0.999,
        "high": close * 1.01,
        "low": close * 0.99,
        "close": close,
        "volume": np.random.randint(100_000_000, 500_000_000, n),
    })


def _make_bear_index_df(n: int = 120, base: float = 3500.0) -> pd.DataFrame:
    """Generate synthetic bearish index data (price below MA100)."""
    np.random.seed(99)
    prices = [base]
    for _ in range(n - 1):
        change = np.random.randn() * 0.005 - 0.003
        prices.append(prices[-1] * (1 + change))
    close = np.array(prices)
    dates = pd.date_range(start="2025-01-01", periods=n, freq="D")
    return pd.DataFrame({
        "date": dates,
        "open": close * 0.999,
        "high": close * 1.01,
        "low": close * 0.99,
        "close": close,
        "volume": np.random.randint(100_000_000, 500_000_000, n),
    })


class TestMarketGuardResult(unittest.TestCase):
    """MarketGuardResult has expected fields."""

    def test_result_fields(self):
        from src.core.market_guard import MarketGuardResult
        r = MarketGuardResult(
            is_safe=True,
            index_code="sh000001",
            index_price=3200.0,
            index_ma100=3100.0,
            message="Market above MA100",
        )
        self.assertTrue(r.is_safe)
        self.assertEqual(r.index_code, "sh000001")
        self.assertGreater(r.index_price, 0)
        self.assertGreater(r.index_ma100, 0)

    def test_default_unsafe(self):
        from src.core.market_guard import MarketGuardResult
        r = MarketGuardResult()
        self.assertFalse(r.is_safe)


class TestMarketGuardCheck(unittest.TestCase):
    """MarketGuard.check() returns correct safety assessment."""

    def test_safe_when_above_ma100(self):
        from src.core.market_guard import MarketGuard
        df = _make_index_df(n=120, trend=0.002)
        mock_fetcher = MagicMock()
        mock_fetcher.get_daily_data.return_value = (df, "mock")
        guard = MarketGuard(fetcher_manager=mock_fetcher, index_code="sz399001")
        result = guard.check()
        self.assertTrue(result.is_safe)
        self.assertGreater(result.index_ma100, 0)

    def test_unsafe_when_below_ma100(self):
        from src.core.market_guard import MarketGuard
        df = _make_bear_index_df(n=120)
        mock_fetcher = MagicMock()
        mock_fetcher.get_daily_data.return_value = (df, "mock")
        guard = MarketGuard(fetcher_manager=mock_fetcher, index_code="sz399001")
        result = guard.check()
        self.assertFalse(result.is_safe)

    def test_graceful_on_fetch_failure(self):
        """When data fetch fails, default to safe (don't block analysis)."""
        from src.core.market_guard import MarketGuard
        mock_fetcher = MagicMock()
        mock_fetcher.get_daily_data.side_effect = Exception("network error")
        guard = MarketGuard(fetcher_manager=mock_fetcher, index_code="sz399001")
        result = guard.check()
        self.assertTrue(result.is_safe)
        self.assertIn("error", result.message.lower())

    def test_graceful_on_empty_data(self):
        from src.core.market_guard import MarketGuard
        mock_fetcher = MagicMock()
        mock_fetcher.get_daily_data.return_value = (pd.DataFrame(), "mock")
        guard = MarketGuard(fetcher_manager=mock_fetcher, index_code="sz399001")
        result = guard.check()
        self.assertTrue(result.is_safe)

    def test_graceful_on_insufficient_data(self):
        from src.core.market_guard import MarketGuard
        df = _make_index_df(n=30)
        mock_fetcher = MagicMock()
        mock_fetcher.get_daily_data.return_value = (df, "mock")
        guard = MarketGuard(fetcher_manager=mock_fetcher, index_code="sz399001")
        result = guard.check()
        self.assertTrue(result.is_safe)
        self.assertIn("insufficient", result.message.lower())

    def test_fetcher_called_with_enough_days(self):
        from src.core.market_guard import MarketGuard
        df = _make_index_df(n=120)
        mock_fetcher = MagicMock()
        mock_fetcher.get_daily_data.return_value = (df, "mock")
        guard = MarketGuard(fetcher_manager=mock_fetcher, index_code="sz399001")
        guard.check()
        call_args = mock_fetcher.get_daily_data.call_args
        self.assertGreaterEqual(call_args[1].get("days", call_args[0][1] if len(call_args[0]) > 1 else 0), 120)


class TestMarketGuardCustomIndex(unittest.TestCase):
    """MarketGuard supports custom index code."""

    def test_custom_index_code(self):
        from src.core.market_guard import MarketGuard
        df = _make_index_df(n=120)
        mock_fetcher = MagicMock()
        mock_fetcher.get_daily_data.return_value = (df, "mock")
        guard = MarketGuard(fetcher_manager=mock_fetcher, index_code="sz399001")
        result = guard.check()
        self.assertEqual(result.index_code, "sz399001")

    def test_shanghai_composite_uses_dedicated_index_history(self):
        from src.core.market_guard import MarketGuard

        df = _make_index_df(n=120)
        mock_fetcher = MagicMock()
        mock_akshare = types.SimpleNamespace(
            stock_zh_index_daily=MagicMock(return_value=df)
        )

        with patch.dict(sys.modules, {"akshare": mock_akshare}):
            guard = MarketGuard(fetcher_manager=mock_fetcher, index_code="sh000001")
            guard.check()

        mock_akshare.stock_zh_index_daily.assert_called_once_with(symbol="sh000001")
        mock_fetcher.get_daily_data.assert_not_called()


if __name__ == "__main__":
    unittest.main()
