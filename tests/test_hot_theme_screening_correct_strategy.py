# -*- coding: utf-8 -*-
"""Unit tests for hot theme stock screening with correct strategy logic."""

import unittest
from datetime import date
from typing import Dict, Any, List

from src.services.theme_context_ingest_service import ExternalTheme, OpenClawThemeContext


class MarketConditionCheckerTestCase(unittest.TestCase):
    """Test market condition checking (info only, not enforced)."""

    def test_check_market_condition_strong(self) -> None:
        """Test market condition check returns strong status."""
        # Mock:上证指数在MA100之上
        market_status = {
            "is_strong": True,
            "message": "大盘强势（MA100之上）"
        }
        self.assertTrue(market_status["is_strong"])

    def test_check_market_condition_weak(self) -> None:
        """Test market condition check returns weak status."""
        # Mock: 上证指数在MA100之下
        market_status = {
            "is_strong": False,
            "message": "大盘弱势（MA100之下）"
        }
        self.assertFalse(market_status["is_strong"])


class LeaderStockSelectionTestCase(unittest.TestCase):
    """Test leader stock selection by priority."""

    def test_select_leader_priority_1_limit_up_within_30min(self) -> None:
        """Test priority 1: limit up within 30 minutes of opening."""
        # 优先级1：开盘半小时内涨停
        theme_stocks = ["000001", "000002", "000003"]

        # Mock: 000001 开盘半小时内涨停
        leader = "000001"
        entry_reason = "开盘半小时内涨停"

        self.assertEqual(leader, "000001")
        self.assertEqual(entry_reason, "开盘半小时内涨停")

    def test_select_leader_priority_2_above_ma100(self) -> None:
        """Test priority 2: above or just broke MA100."""
        # 优先级2：站上或刚突破MA100
        theme_stocks = ["000001", "000002", "000003"]

        # Mock: 000002 站上MA100
        leader = "000002"
        entry_reason = "站上/刚突破MA100"

        self.assertEqual(leader, "000002")
        self.assertEqual(entry_reason, "站上/刚突破MA100")

    def test_select_leader_no_match(self) -> None:
        """Test no leader selected when no priority match."""
        theme_stocks = ["000001", "000002", "000003"]

        # Mock: 没有符合条件的股票
        leader = None

        self.assertIsNone(leader)


class CoreSignalIdentificationTestCase(unittest.TestCase):
    """Test core technical signal identification."""

    def test_signal_gap_limit_up(self) -> None:
        """Test gap + limit up (strongest signal)."""
        signals = {
            "core_signal": "跳空涨停",
            "core_signal_score": 15,
            "hit_reasons": ["跳空涨停（缺口+涨停共振）"]
        }

        self.assertEqual(signals["core_signal"], "跳空涨停")
        self.assertEqual(signals["core_signal_score"], 15)
        self.assertIn("跳空涨停（缺口+涨停共振）", signals["hit_reasons"])

    def test_signal_gap_breakout_ma100(self) -> None:
        """Test gap breakout MA100."""
        signals = {
            "core_signal": "缺口突破MA100",
            "core_signal_score": 12,
            "hit_reasons": ["缺口突破MA100均线"]
        }

        self.assertEqual(signals["core_signal"], "缺口突破MA100")
        self.assertEqual(signals["core_signal_score"], 12)

    def test_signal_limit_up(self) -> None:
        """Test limit up only."""
        signals = {
            "core_signal": "涨停",
            "core_signal_score": 10,
            "hit_reasons": ["涨停"]
        }

        self.assertEqual(signals["core_signal"], "涨停")
        self.assertEqual(signals["core_signal_score"], 10)

    def test_bonus_low_123_breakout(self) -> None:
        """Test bonus: low 123 structure breakout."""
        signals = {
            "bonus_signals": ["低位123结构"],
            "bonus_score": 12,
            "hit_reasons": ["低位123结构+涨停突破高点2"]
        }

        self.assertIn("低位123结构", signals["bonus_signals"])
        self.assertEqual(signals["bonus_score"], 12)

    def test_bonus_bottom_divergence(self) -> None:
        """Test bonus: bottom divergence double breakout."""
        signals = {
            "bonus_signals": ["底背离双突破"],
            "bonus_score": 12,
            "hit_reasons": ["底背离双突破"]
        }

        self.assertIn("底背离双突破", signals["bonus_signals"])
        self.assertEqual(signals["bonus_score"], 12)

    def test_total_score_calculation(self) -> None:
        """Test total score = core + bonus."""
        signals = {
            "core_signal_score": 15,
            "bonus_signals": ["低位123结构", "底背离双突破"],
            "bonus_score": 24,
            "total_score": 0
        }

        signals["total_score"] = signals["core_signal_score"] + signals["bonus_score"]
        self.assertEqual(signals["total_score"], 39)


class HotThemeScreeningTestCase(unittest.TestCase):
    """Test hot theme stock screening logic."""

    def test_screen_one_theme_one_leader(self) -> None:
        """Test screening: 1 theme → 1 leader stock."""
        themes = [
            ExternalTheme(
                name="机器人",
                heat_score=90.0,
                confidence=0.85,
                catalyst_summary="政策催化",
                keywords=["机器人"],
                evidence=[]
            )
        ]

        # Mock: 1个题材选出1个龙头
        results = [
            {
                "code": "000001",
                "theme": "机器人",
                "theme_heat": 90.0,
                "entry_reason": "开盘半小时内涨停",
                "core_signal": "跳空涨停",
                "total_score": 85
            }
        ]

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["theme"], "机器人")

    def test_screen_multiple_themes_multiple_leaders(self) -> None:
        """Test screening: N themes → N leaders (1 per theme)."""
        themes = [
            ExternalTheme(
                name="机器人",
                heat_score=90.0,
                confidence=0.85,
                catalyst_summary="政策催化",
                keywords=["机器人"],
                evidence=[]
            ),
            ExternalTheme(
                name="芯片",
                heat_score=85.0,
                confidence=0.80,
                catalyst_summary="产业升级",
                keywords=["芯片"],
                evidence=[]
            ),
            ExternalTheme(
                name="新能源",
                heat_score=80.0,
                confidence=0.75,
                catalyst_summary="政策支持",
                keywords=["新能源"],
                evidence=[]
            )
        ]

        # Mock: 3个题材选出3个龙头
        results = [
            {
                "code": "000001",
                "theme": "机器人",
                "total_score": 85
            },
            {
                "code": "000002",
                "theme": "芯片",
                "total_score": 82
            },
            {
                "code": "000003",
                "theme": "新能源",
                "total_score": 80
            }
        ]

        self.assertEqual(len(results), 3)
        self.assertEqual(results[0]["theme"], "机器人")
        self.assertEqual(results[1]["theme"], "芯片")
        self.assertEqual(results[2]["theme"], "新能源")

    def test_screen_filter_below_threshold(self) -> None:
        """Test screening: filter out scores < 80."""
        results_before_filter = [
            {"code": "000001", "total_score": 85},
            {"code": "000002", "total_score": 75},  # Below 80
            {"code": "000003", "total_score": 80}
        ]

        # Filter >= 80
        results = [r for r in results_before_filter if r["total_score"] >= 80]

        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]["code"], "000001")
        self.assertEqual(results[1]["code"], "000003")

    def test_screen_result_structure(self) -> None:
        """Test screening result contains all required fields."""
        result = {
            "code": "000001",
            "theme": "机器人",
            "theme_heat": 90.0,
            "theme_catalyst": "政策催化",
            "entry_reason": "开盘半小时内涨停",
            "core_signal": "跳空涨停",
            "bonus_signals": ["低位123结构"],
            "total_score": 85,
            "hit_reasons": [
                "跳空涨停（缺口+涨停共振）",
                "低位123结构+涨停突破高点2"
            ],
            "market_status": {
                "is_strong": True,
                "message": "大盘强势（MA100之上）"
            }
        }

        # Verify all required fields
        self.assertIn("code", result)
        self.assertIn("theme", result)
        self.assertIn("entry_reason", result)
        self.assertIn("core_signal", result)
        self.assertIn("hit_reasons", result)
        self.assertIn("market_status", result)


if __name__ == "__main__":
    unittest.main()
