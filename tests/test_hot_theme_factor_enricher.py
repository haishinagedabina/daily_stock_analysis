# -*- coding: utf-8 -*-
"""Unit tests for HotThemeFactorEnricher."""

import unittest
from src.services.hot_theme_factor_enricher import HotThemeFactorEnricher
from src.services.theme_context_ingest_service import ExternalTheme, OpenClawThemeContext
from datetime import datetime


class HotThemeFactorEnricherTestCase(unittest.TestCase):
    """Test HotThemeFactorEnricher."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        self.enricher = HotThemeFactorEnricher()

    def test_enrich_snapshot_no_theme_context(self) -> None:
        """Test enriching snapshot with no theme context."""
        snapshot = {
            "code": "000001",
            "name": "机器人",
            "close": 10.5,
            "above_ma100": True,
        }

        enriched = self.enricher.enrich_snapshot(snapshot, theme_context=None)

        self.assertFalse(enriched["is_hot_theme_stock"])
        self.assertIsNone(enriched["primary_theme"])
        self.assertEqual(enriched["theme_match_score"], 0.0)
        self.assertEqual(enriched["leader_score"], 0)
        self.assertEqual(enriched["extreme_strength_score"], 0.0)

    def test_enrich_snapshot_with_matching_theme(self) -> None:
        """Test enriching snapshot with matching theme."""
        snapshot = {
            "code": "000001",
            "name": "机器人",
            "close": 10.5,
            "above_ma100": True,
            "gap_breakaway": True,
            "pattern_123_low_trendline": False,
            "is_limit_up": True,
            "bottom_divergence_double_breakout": False,
            "volume_ratio": 1.5,
            "turnover_rate": 0.05,
            "circ_mv": 75_000_000_000,
            "breakout_ratio": 1.2,
            "ma100_breakout_days": 3,
        }

        theme = ExternalTheme(
            name="机器人",
            heat_score=90.0,
            confidence=0.85,
            catalyst_summary="政策催化",
            keywords=["机器人"],
            evidence=[],
        )

        theme_context = OpenClawThemeContext(
            source="openclaw",
            trade_date="2026-03-26",
            market="cn",
            themes=[theme],
            accepted_at=datetime.now().isoformat(),
        )

        enriched = self.enricher.enrich_snapshot(
            snapshot,
            theme_context=theme_context,
            boards=["机器人"],
        )

        self.assertTrue(enriched["is_hot_theme_stock"])
        self.assertEqual(enriched["primary_theme"], "机器人")
        self.assertGreater(enriched["theme_match_score"], 0.8)
        self.assertGreater(enriched["leader_score"], 50)
        self.assertGreater(enriched["extreme_strength_score"], 70)
        self.assertIn("MA100之上", enriched["extreme_strength_reasons"])
        self.assertIn("跳空突破", enriched["extreme_strength_reasons"])
        self.assertIn("涨停", enriched["extreme_strength_reasons"])

    def test_enrich_snapshot_no_matching_theme(self) -> None:
        """Test enriching snapshot with no matching theme."""
        snapshot = {
            "code": "000002",
            "name": "芯片",
            "close": 10.5,
            "above_ma100": True,
            "gap_breakaway": False,
            "pattern_123_low_trendline": False,
            "is_limit_up": False,
            "bottom_divergence_double_breakout": False,
            "volume_ratio": 1.0,
            "turnover_rate": 0.02,
            "circ_mv": 150_000_000_000,
            "breakout_ratio": 0.95,
            "ma100_breakout_days": 0,
        }

        theme = ExternalTheme(
            name="机器人",
            heat_score=90.0,
            confidence=0.85,
            catalyst_summary="政策催化",
            keywords=["机器人"],
            evidence=[],
        )

        theme_context = OpenClawThemeContext(
            source="openclaw",
            trade_date="2026-03-26",
            market="cn",
            themes=[theme],
            accepted_at=datetime.now().isoformat(),
        )

        enriched = self.enricher.enrich_snapshot(
            snapshot,
            theme_context=theme_context,
            boards=["芯片"],
        )

        self.assertFalse(enriched["is_hot_theme_stock"])
        self.assertIsNone(enriched["primary_theme"])
        self.assertEqual(enriched["leader_score"], 0)
        self.assertEqual(enriched["extreme_strength_score"], 0.0)

    def test_enrich_snapshot_multiple_themes(self) -> None:
        """Test enriching snapshot with multiple themes (picks best match)."""
        snapshot = {
            "code": "000001",
            "name": "机器人",
            "close": 10.5,
            "above_ma100": True,
            "gap_breakaway": True,
            "pattern_123_low_trendline": False,
            "is_limit_up": True,
            "bottom_divergence_double_breakout": False,
            "volume_ratio": 1.5,
            "turnover_rate": 0.05,
            "circ_mv": 75_000_000_000,
            "breakout_ratio": 1.2,
            "ma100_breakout_days": 3,
        }

        themes = [
            ExternalTheme(
                name="芯片",
                heat_score=80.0,
                confidence=0.80,
                catalyst_summary="产业升级",
                keywords=["芯片"],
                evidence=[],
            ),
            ExternalTheme(
                name="机器人",
                heat_score=90.0,
                confidence=0.85,
                catalyst_summary="政策催化",
                keywords=["机器人"],
                evidence=[],
            ),
        ]

        theme_context = OpenClawThemeContext(
            source="openclaw",
            trade_date="2026-03-26",
            market="cn",
            themes=themes,
            accepted_at=datetime.now().isoformat(),
        )

        enriched = self.enricher.enrich_snapshot(
            snapshot,
            theme_context=theme_context,
            boards=["机器人"],
        )

        # Should pick "机器人" as best match
        self.assertTrue(enriched["is_hot_theme_stock"])
        self.assertEqual(enriched["primary_theme"], "机器人")
        self.assertEqual(enriched["theme_heat_score"], 90.0)

    def test_enrich_snapshot_preserves_original_fields(self) -> None:
        """Test enriching snapshot preserves original fields."""
        snapshot = {
            "code": "000001",
            "name": "机器人",
            "close": 10.5,
            "above_ma100": True,
            "gap_breakaway": True,
            "pattern_123_low_trendline": False,
            "is_limit_up": True,
            "bottom_divergence_double_breakout": False,
            "volume_ratio": 1.5,
            "turnover_rate": 0.05,
            "circ_mv": 75_000_000_000,
            "breakout_ratio": 1.2,
            "ma100_breakout_days": 3,
        }

        enriched = self.enricher.enrich_snapshot(snapshot, theme_context=None)

        # Original fields should be preserved
        self.assertEqual(enriched["code"], "000001")
        self.assertEqual(enriched["name"], "机器人")
        self.assertEqual(enriched["close"], 10.5)
        self.assertTrue(enriched["above_ma100"])


if __name__ == "__main__":
    unittest.main()
