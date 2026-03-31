# -*- coding: utf-8 -*-
"""
TDD RED 阶段：MarketEnvironmentEngine 单元测试。

测试目标：
1. aggressive 环境判定（指数>MA100, MA20↑, 赚钱效应好）
2. balanced 环境判定（指数>MA100, 赚钱效应中性）
3. defensive 环境判定（指数<MA100, MA20企稳或涨跌比>0.8）
4. stand_aside 环境判定（指数<MA100, MA20↓, 赚钱效应差）
5. risk_level 与 regime 联动
6. 边界条件（缺失数据、不足数据）
"""

import unittest
from datetime import date, timedelta

import numpy as np
import pandas as pd

from src.core.market_guard import MarketGuardResult
from src.schemas.trading_types import MarketEnvironment, MarketRegime, RiskLevel
from src.services.market_environment_engine import MarketEnvironmentEngine


def _make_index_bars(n: int = 30, start_close: float = 3200.0,
                     slope: float = 0.0) -> pd.DataFrame:
    """生成合成指数日线数据。

    Args:
        n: 数据行数
        start_close: 起始收盘价
        slope: 每日涨跌幅（正=上升趋势, 负=下降趋势, 0=横盘）
    """
    dates = [date(2026, 1, 1) + timedelta(days=i) for i in range(n)]
    closes = [start_close + slope * i for i in range(n)]
    return pd.DataFrame({"date": dates, "close": closes})


def _make_guard_result(is_safe: bool, index_price: float = 3300.0,
                       index_ma100: float = 3200.0) -> MarketGuardResult:
    return MarketGuardResult(
        is_safe=is_safe,
        index_code="sh000001",
        index_price=index_price,
        index_ma100=index_ma100,
        message="test",
    )


def _make_market_stats(
    up_count: int = 2500,
    down_count: int = 2000,
    limit_up_count: int = 60,
    limit_down_count: int = 10,
    total_amount: float = 12000.0,
) -> dict:
    return {
        "up_count": up_count,
        "down_count": down_count,
        "flat_count": 500,
        "limit_up_count": limit_up_count,
        "limit_down_count": limit_down_count,
        "total_amount": total_amount,
    }


class AggressiveRegimeTestCase(unittest.TestCase):
    """aggressive 环境：指数>MA100, MA20↑, 赚钱效应好"""

    def setUp(self) -> None:
        self.engine = MarketEnvironmentEngine()

    def test_aggressive_regime(self) -> None:
        """典型强势市场。"""
        guard = _make_guard_result(is_safe=True, index_price=3400.0, index_ma100=3200.0)
        bars = _make_index_bars(n=30, start_close=3200.0, slope=8.0)  # MA20 上升
        stats = _make_market_stats(
            up_count=3000, down_count=1800,
            limit_up_count=80, limit_down_count=5,
        )

        result = self.engine.assess(guard, bars, stats)

        self.assertIsInstance(result, MarketEnvironment)
        self.assertEqual(result.regime, MarketRegime.AGGRESSIVE)
        self.assertEqual(result.risk_level, RiskLevel.LOW)
        self.assertTrue(result.is_safe)

    def test_aggressive_carries_index_data(self) -> None:
        """结果应包含指数价格和 MA100。"""
        guard = _make_guard_result(is_safe=True, index_price=3400.0, index_ma100=3200.0)
        bars = _make_index_bars(n=30, slope=8.0)
        stats = _make_market_stats(limit_up_count=80, limit_down_count=5)

        result = self.engine.assess(guard, bars, stats)

        self.assertAlmostEqual(result.index_price, 3400.0, places=1)
        self.assertAlmostEqual(result.index_ma100, 3200.0, places=1)


class BalancedRegimeTestCase(unittest.TestCase):
    """balanced 环境：指数>MA100, 中性赚钱效应或 MA20 横盘"""

    def setUp(self) -> None:
        self.engine = MarketEnvironmentEngine()

    def test_balanced_above_ma100_flat_trend(self) -> None:
        """指数>MA100 但 MA20 横盘 → balanced。"""
        guard = _make_guard_result(is_safe=True, index_price=3250.0, index_ma100=3200.0)
        bars = _make_index_bars(n=30, start_close=3250.0, slope=0.0)  # 横盘
        stats = _make_market_stats(
            up_count=2500, down_count=2300,
            limit_up_count=30, limit_down_count=20,
        )

        result = self.engine.assess(guard, bars, stats)

        self.assertEqual(result.regime, MarketRegime.BALANCED)
        self.assertEqual(result.risk_level, RiskLevel.MEDIUM)

    def test_balanced_above_ma100_neutral_money_effect(self) -> None:
        """指数>MA100, MA20↑ 但赚钱效应中性 → balanced。"""
        guard = _make_guard_result(is_safe=True, index_price=3300.0, index_ma100=3200.0)
        bars = _make_index_bars(n=30, start_close=3200.0, slope=3.0)  # 缓升
        stats = _make_market_stats(
            up_count=2500, down_count=2200,
            limit_up_count=30, limit_down_count=25,  # 涨停≈跌停，不够 aggressive
        )

        result = self.engine.assess(guard, bars, stats)

        self.assertEqual(result.regime, MarketRegime.BALANCED)


class DefensiveRegimeTestCase(unittest.TestCase):
    """defensive 环境：指数<MA100, MA20 企稳或涨跌比>0.8"""

    def setUp(self) -> None:
        self.engine = MarketEnvironmentEngine()

    def test_defensive_below_ma100_stabilizing(self) -> None:
        """指数<MA100 但 MA20 企稳 → defensive。"""
        guard = _make_guard_result(is_safe=False, index_price=3100.0, index_ma100=3200.0)
        bars = _make_index_bars(n=30, start_close=3100.0, slope=0.5)  # 微升=企稳
        stats = _make_market_stats(
            up_count=2200, down_count=2600,
            limit_up_count=20, limit_down_count=15,
        )

        result = self.engine.assess(guard, bars, stats)

        self.assertEqual(result.regime, MarketRegime.DEFENSIVE)
        self.assertEqual(result.risk_level, RiskLevel.HIGH)
        self.assertFalse(result.is_safe)

    def test_defensive_below_ma100_good_breadth(self) -> None:
        """指数<MA100 但涨跌比>0.8 → defensive（不跌到 stand_aside）。"""
        guard = _make_guard_result(is_safe=False, index_price=3150.0, index_ma100=3200.0)
        bars = _make_index_bars(n=30, start_close=3100.0, slope=-2.0)  # MA20↓
        stats = _make_market_stats(
            up_count=2300, down_count=2500,  # ratio=0.92>0.8
            limit_up_count=25, limit_down_count=20,
        )

        result = self.engine.assess(guard, bars, stats)

        self.assertEqual(result.regime, MarketRegime.DEFENSIVE)


class StandAsideRegimeTestCase(unittest.TestCase):
    """stand_aside 环境：指数<MA100, MA20↓, 赚钱效应差"""

    def setUp(self) -> None:
        self.engine = MarketEnvironmentEngine()

    def test_stand_aside_full_conditions(self) -> None:
        """全面弱势市场。"""
        guard = _make_guard_result(is_safe=False, index_price=3000.0, index_ma100=3200.0)
        bars = _make_index_bars(n=30, start_close=3200.0, slope=-8.0)  # 强下跌
        stats = _make_market_stats(
            up_count=1500, down_count=3200,
            limit_up_count=5, limit_down_count=60,  # 跌停>涨停
        )

        result = self.engine.assess(guard, bars, stats)

        self.assertEqual(result.regime, MarketRegime.STAND_ASIDE)
        self.assertEqual(result.risk_level, RiskLevel.HIGH)
        self.assertFalse(result.is_safe)

    def test_stand_aside_message_not_empty(self) -> None:
        """stand_aside 应有描述性消息。"""
        guard = _make_guard_result(is_safe=False, index_price=3000.0, index_ma100=3200.0)
        bars = _make_index_bars(n=30, start_close=3200.0, slope=-8.0)
        stats = _make_market_stats(
            up_count=1500, down_count=3200,
            limit_up_count=5, limit_down_count=60,
        )

        result = self.engine.assess(guard, bars, stats)

        self.assertTrue(len(result.message) > 0)


class EdgeCasesTestCase(unittest.TestCase):
    """边界条件和降级行为。"""

    def setUp(self) -> None:
        self.engine = MarketEnvironmentEngine()

    def test_missing_market_stats_defaults_by_ma100(self) -> None:
        """market_stats 为 None 时基于 MA100 降级判断。"""
        guard = _make_guard_result(is_safe=True, index_price=3300.0, index_ma100=3200.0)
        bars = _make_index_bars(n=30, slope=3.0)

        result = self.engine.assess(guard, bars, market_stats=None)

        # 指数>MA100, 无赚钱效应数据 → balanced（保守）
        self.assertIn(result.regime, [MarketRegime.BALANCED, MarketRegime.AGGRESSIVE])

    def test_missing_market_stats_below_ma100(self) -> None:
        """指数<MA100, market_stats 为 None → defensive。"""
        guard = _make_guard_result(is_safe=False, index_price=3100.0, index_ma100=3200.0)
        bars = _make_index_bars(n=30, slope=-3.0)

        result = self.engine.assess(guard, bars, market_stats=None)

        self.assertIn(result.regime, [MarketRegime.DEFENSIVE, MarketRegime.STAND_ASIDE])

    def test_insufficient_bars_uses_guard_only(self) -> None:
        """bars 数据不足 20 行 → 仅用 guard_result 判定。"""
        guard = _make_guard_result(is_safe=True, index_price=3300.0, index_ma100=3200.0)
        bars = _make_index_bars(n=5, slope=3.0)  # 不足 20 行
        stats = _make_market_stats()

        result = self.engine.assess(guard, bars, stats)

        # 仍应给出有效 regime，不应报错
        self.assertIsInstance(result.regime, MarketRegime)
        self.assertTrue(result.is_safe)

    def test_empty_bars_does_not_crash(self) -> None:
        """空 DataFrame 不报错。"""
        guard = _make_guard_result(is_safe=True, index_price=3300.0, index_ma100=3200.0)
        bars = pd.DataFrame(columns=["date", "close"])
        stats = _make_market_stats()

        result = self.engine.assess(guard, bars, stats)

        self.assertIsInstance(result, MarketEnvironment)

    def test_none_bars_does_not_crash(self) -> None:
        """bars 为 None 不报错。"""
        guard = _make_guard_result(is_safe=True, index_price=3300.0, index_ma100=3200.0)
        stats = _make_market_stats()

        result = self.engine.assess(guard, None, stats)

        self.assertIsInstance(result, MarketEnvironment)

    def test_guard_error_defaults_safe(self) -> None:
        """guard 报错（is_safe=True, price=0）→ 仍应输出有效结果。"""
        guard = MarketGuardResult(
            is_safe=True, index_code="sh000001",
            index_price=0.0, index_ma100=0.0,
            message="Error fetching data",
        )
        bars = pd.DataFrame(columns=["date", "close"])
        stats = _make_market_stats()

        result = self.engine.assess(guard, bars, stats)

        self.assertIsInstance(result, MarketEnvironment)
        self.assertTrue(result.is_safe)


if __name__ == "__main__":
    unittest.main()
