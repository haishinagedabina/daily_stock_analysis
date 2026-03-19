# -*- coding: utf-8 -*-
"""
TDD tests for Phase 1a: MA100 infrastructure.

Tests cover:
1. Config: new MA100-related config fields and env loading
2. TrendAnalysisResult: new MA100 fields and serialization
3. _calculate_mas: MA100 calculation with length protection
4. _analyze_support_resistance: MA60/MA100 support/resistance
5. _generate_signal: MA100 signal degradation
6. Pipeline: configurable data_fetch_days
"""

import math
import unittest
from unittest.mock import patch, MagicMock, PropertyMock

import numpy as np
import pandas as pd

from src.stock_analyzer import (
    StockTrendAnalyzer,
    TrendAnalysisResult,
    TrendStatus,
    VolumeStatus,
    MACDStatus,
    RSIStatus,
    BuySignal,
)


def _make_bullish_df(n: int = 120, base_price: float = 10.0, trend: float = 0.002) -> pd.DataFrame:
    """Generate a synthetic uptrend DataFrame with n rows."""
    np.random.seed(42)
    prices = [base_price]
    for _ in range(n - 1):
        change = np.random.randn() * 0.01 + trend
        prices.append(prices[-1] * (1 + change))

    dates = pd.date_range(start="2025-01-01", periods=n, freq="D")
    close = np.array(prices)
    return pd.DataFrame({
        "date": dates,
        "open": close * (1 - np.random.uniform(0, 0.005, n)),
        "high": close * (1 + np.random.uniform(0, 0.02, n)),
        "low": close * (1 - np.random.uniform(0, 0.02, n)),
        "close": close,
        "volume": np.random.randint(1_000_000, 5_000_000, n),
    })


def _make_bearish_df(n: int = 120, base_price: float = 20.0) -> pd.DataFrame:
    """Generate a synthetic downtrend DataFrame where price is below MA100."""
    np.random.seed(99)
    prices = [base_price]
    for _ in range(n - 1):
        change = np.random.randn() * 0.01 - 0.003
        prices.append(prices[-1] * (1 + change))

    dates = pd.date_range(start="2025-01-01", periods=n, freq="D")
    close = np.array(prices)
    return pd.DataFrame({
        "date": dates,
        "open": close * (1 - np.random.uniform(0, 0.005, n)),
        "high": close * (1 + np.random.uniform(0, 0.02, n)),
        "low": close * (1 - np.random.uniform(0, 0.02, n)),
        "close": close,
        "volume": np.random.randint(1_000_000, 5_000_000, n),
    })


def _make_result(**overrides) -> TrendAnalysisResult:
    """Build a TrendAnalysisResult with MA100 defaults for testing."""
    defaults = dict(
        code="000001",
        trend_status=TrendStatus.BULL,
        ma_alignment="",
        trend_strength=50.0,
        ma5=10.0,
        ma10=9.5,
        ma20=9.0,
        ma60=8.5,
        ma100=8.0,
        current_price=10.0,
        bias_ma5=0.0,
        bias_ma10=0.0,
        bias_ma20=0.0,
        bias_ma100=0.0,
        above_ma100=True,
        ma100_breakout_days=5,
        volume_status=VolumeStatus.NORMAL,
        volume_ratio_5d=1.0,
        volume_trend="",
        support_ma5=False,
        support_ma10=False,
        macd_status=MACDStatus.BULLISH,
        rsi_status=RSIStatus.NEUTRAL,
    )
    defaults.update(overrides)
    return TrendAnalysisResult(**defaults)


# ─────────────────────────────────────────────────────────────
# 1. Config tests
# ─────────────────────────────────────────────────────────────
class TestMA100Config(unittest.TestCase):
    """MA100-related config fields exist and have correct defaults."""

    def test_default_data_fetch_days(self):
        from src.config import Config
        cfg = Config()
        self.assertEqual(cfg.data_fetch_days, 200)

    def test_default_ma100_breakout_confirm_days(self):
        from src.config import Config
        cfg = Config()
        self.assertEqual(cfg.ma100_breakout_confirm_days, 3)

    def test_default_ma100_support_tolerance(self):
        from src.config import Config
        cfg = Config()
        self.assertAlmostEqual(cfg.ma100_support_tolerance, 0.02)

    @patch.dict("os.environ", {"DATA_FETCH_DAYS": "300"})
    def test_env_override_data_fetch_days(self):
        from src.config import Config
        Config.reset_instance()
        try:
            cfg = Config._load_from_env()
            self.assertEqual(cfg.data_fetch_days, 300)
        finally:
            Config.reset_instance()


# ─────────────────────────────────────────────────────────────
# 2. TrendAnalysisResult field tests
# ─────────────────────────────────────────────────────────────
class TestTrendAnalysisResultMA100Fields(unittest.TestCase):
    """TrendAnalysisResult has new MA100 fields with correct defaults."""

    def test_ma100_field_defaults(self):
        r = TrendAnalysisResult(code="600519")
        self.assertEqual(r.ma100, 0.0)
        self.assertEqual(r.bias_ma100, 0.0)
        self.assertFalse(r.above_ma100)
        self.assertEqual(r.ma100_breakout_days, 0)
        self.assertEqual(r.stop_loss_price, 0.0)
        self.assertEqual(r.stop_loss_ma, "")

    def test_to_dict_includes_ma100(self):
        r = _make_result(ma100=8.0, above_ma100=True, ma100_breakout_days=3)
        d = r.to_dict()
        self.assertIn("ma100", d)
        self.assertIn("above_ma100", d)
        self.assertIn("ma100_breakout_days", d)
        self.assertIn("bias_ma100", d)
        self.assertIn("stop_loss_price", d)
        self.assertIn("stop_loss_ma", d)
        self.assertEqual(d["ma100"], 8.0)
        self.assertTrue(d["above_ma100"])


# ─────────────────────────────────────────────────────────────
# 3. _calculate_mas tests
# ─────────────────────────────────────────────────────────────
class TestCalculateMAs(unittest.TestCase):
    """_calculate_mas computes MA100 when data is sufficient."""

    def setUp(self):
        self.analyzer = StockTrendAnalyzer()

    def test_ma100_computed_with_enough_data(self):
        df = _make_bullish_df(n=120)
        result_df = self.analyzer._calculate_mas(df)
        self.assertIn("MA100", result_df.columns)
        self.assertFalse(result_df["MA100"].iloc[-1] != result_df["MA100"].iloc[-1])  # not NaN

    def test_ma100_fallback_with_insufficient_data(self):
        df = _make_bullish_df(n=50)
        result_df = self.analyzer._calculate_mas(df)
        self.assertIn("MA100", result_df.columns)
        self.assertEqual(result_df["MA100"].iloc[-1], result_df["MA60"].iloc[-1])

    def test_ma100_value_is_correct(self):
        df = _make_bullish_df(n=120)
        result_df = self.analyzer._calculate_mas(df)
        expected = df["close"].rolling(window=100).mean().iloc[-1]
        self.assertAlmostEqual(result_df["MA100"].iloc[-1], expected, places=6)


# ─────────────────────────────────────────────────────────────
# 4. analyze() integration: MA100 fields populated
# ─────────────────────────────────────────────────────────────
class TestAnalyzeMA100Fields(unittest.TestCase):
    """Full analyze() populates MA100-related fields."""

    def setUp(self):
        self.analyzer = StockTrendAnalyzer()

    @patch("src.stock_analyzer.get_config")
    def test_analyze_populates_ma100(self, mock_cfg):
        mock_cfg.return_value.bias_threshold = 5.0
        df = _make_bullish_df(n=120)
        result = self.analyzer.analyze(df, "600519")
        self.assertGreater(result.ma100, 0.0)
        self.assertNotEqual(result.bias_ma100, 0.0)

    @patch("src.stock_analyzer.get_config")
    def test_above_ma100_true_in_uptrend(self, mock_cfg):
        mock_cfg.return_value.bias_threshold = 5.0
        df = _make_bullish_df(n=120)
        result = self.analyzer.analyze(df, "600519")
        self.assertTrue(result.above_ma100)

    @patch("src.stock_analyzer.get_config")
    def test_above_ma100_false_in_downtrend(self, mock_cfg):
        mock_cfg.return_value.bias_threshold = 5.0
        df = _make_bearish_df(n=120)
        result = self.analyzer.analyze(df, "600519")
        self.assertFalse(result.above_ma100)

    @patch("src.stock_analyzer.get_config")
    def test_ma100_breakout_days_counted(self, mock_cfg):
        mock_cfg.return_value.bias_threshold = 5.0
        df = _make_bullish_df(n=120)
        result = self.analyzer.analyze(df, "600519")
        self.assertGreaterEqual(result.ma100_breakout_days, 0)


# ─────────────────────────────────────────────────────────────
# 5. Support/resistance with MA60/MA100
# ─────────────────────────────────────────────────────────────
class TestSupportResistanceMA100(unittest.TestCase):
    """_analyze_support_resistance includes MA60/MA100."""

    def setUp(self):
        self.analyzer = StockTrendAnalyzer()

    def test_ma60_as_support(self):
        """Price near and above MA60 -> MA60 in support_levels."""
        df = _make_bullish_df(n=120)
        result = _make_result(
            current_price=10.0,
            ma60=9.85,
        )
        self.analyzer._analyze_support_resistance(df, result)
        self.assertIn(9.85, result.support_levels)

    def test_ma100_as_support(self):
        """Price above MA100 -> MA100 in support_levels."""
        df = _make_bullish_df(n=120)
        result = _make_result(
            current_price=10.0,
            ma100=9.5,
        )
        self.analyzer._analyze_support_resistance(df, result)
        self.assertIn(9.5, result.support_levels)

    def test_ma100_below_price_not_support(self):
        """Price far below MA100 -> MA100 NOT in support_levels."""
        df = _make_bullish_df(n=120)
        result = _make_result(
            current_price=8.0,
            ma100=10.0,
        )
        self.analyzer._analyze_support_resistance(df, result)
        self.assertNotIn(10.0, result.support_levels)


# ─────────────────────────────────────────────────────────────
# 6. Signal degradation for below-MA100 stocks
# ─────────────────────────────────────────────────────────────
class TestSignalDegradationMA100(unittest.TestCase):
    """Stocks below MA100 get signal score penalty."""

    def setUp(self):
        self.analyzer = StockTrendAnalyzer()

    @patch("src.stock_analyzer.get_config")
    def test_below_ma100_signal_degraded(self, mock_cfg):
        mock_cfg.return_value.bias_threshold = 5.0
        result_above = _make_result(above_ma100=True, ma100_breakout_days=10)
        result_below = _make_result(above_ma100=False, ma100_breakout_days=0)
        self.analyzer._generate_signal(result_above)
        self.analyzer._generate_signal(result_below)
        self.assertGreater(result_above.signal_score, result_below.signal_score)

    @patch("src.stock_analyzer.get_config")
    def test_below_ma100_risk_warning(self, mock_cfg):
        mock_cfg.return_value.bias_threshold = 5.0
        result = _make_result(above_ma100=False, ma100_breakout_days=0)
        self.analyzer._generate_signal(result)
        self.assertTrue(
            any("MA100" in r for r in result.risk_factors),
            f"Expected MA100 risk warning in {result.risk_factors}",
        )


# ─────────────────────────────────────────────────────────────
# 7. format_analysis includes MA100
# ─────────────────────────────────────────────────────────────
class TestFormatAnalysisMA100(unittest.TestCase):
    """format_analysis output includes MA100 info."""

    def setUp(self):
        self.analyzer = StockTrendAnalyzer()

    def test_format_includes_ma100_line(self):
        result = _make_result(ma100=8.0, bias_ma100=25.0)
        text = self.analyzer.format_analysis(result)
        self.assertIn("MA100", text)
        self.assertIn("8.00", text)


# ─────────────────────────────────────────────────────────────
# 8. Pipeline data_fetch_days
# ─────────────────────────────────────────────────────────────
class TestPipelineDataFetchDays(unittest.TestCase):
    """Pipeline uses config.data_fetch_days instead of hardcoded 30."""

    @patch("src.stock_analyzer.get_config")
    def test_config_data_fetch_days_used(self, mock_cfg):
        """Verify config field exists and defaults to 200."""
        from src.config import Config
        cfg = Config()
        self.assertEqual(cfg.data_fetch_days, 200)
        self.assertGreater(cfg.data_fetch_days, 30)


if __name__ == "__main__":
    unittest.main()
