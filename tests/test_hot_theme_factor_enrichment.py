# -*- coding: utf-8 -*-
"""Unit tests for hot theme stock factor enrichment."""

import unittest
from datetime import date
from typing import Dict, Any

from src.services.theme_matching_service import ThemeMatchingService
from src.services.leader_score_calculator import LeaderScoreCalculator
from src.services.extreme_strength_scorer import ExtremeStrengthScorer
from src.services.theme_context_ingest_service import ExternalTheme


class HotThemeFactorEnrichmentTestCase(unittest.TestCase):
    """Test hot theme factor enrichment in factor snapshot."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        self.theme_matcher = ThemeMatchingService()
        self.leader_calculator = LeaderScoreCalculator()
        self.strength_scorer = ExtremeStrengthScorer()

    def test_enrich_factor_snapshot_with_theme_match(self) -> None:
        """Test enriching factor snapshot with theme match."""
        # Simulate a factor snapshot
        factor_snapshot = {
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
            "trend_score": 70,
        }

        # Simulate theme context
        theme = ExternalTheme(
            name="机器人",
            heat_score=90.0,
            confidence=0.85,
            catalyst_summary="政策催化",
            keywords=["机器人"],
            evidence=[],
        )

        # Simulate board info
        boards = ["机器人"]

        # Enrich snapshot
        is_hot = self.theme_matcher.is_hot_theme_stock(
            boards=boards,
            stock_name=factor_snapshot["name"],
            theme_name=theme.name,
            keywords=theme.keywords,
        )
        theme_match_score = self.theme_matcher.calculate_theme_match_score(
            boards=boards,
            stock_name=factor_snapshot["name"],
            theme_name=theme.name,
            keywords=theme.keywords,
        )

        leader_score = self.leader_calculator.calculate_leader_score(
            theme_match_score=theme_match_score,
            circ_mv=factor_snapshot["circ_mv"],
            turnover_rate=factor_snapshot["turnover_rate"],
            is_limit_up=factor_snapshot["is_limit_up"],
            gap_breakaway=factor_snapshot["gap_breakaway"],
            above_ma100=factor_snapshot["above_ma100"],
            ma100_breakout_days=3,
        )

        extreme_strength_score = self.strength_scorer.calculate_extreme_strength_score(
            above_ma100=factor_snapshot["above_ma100"],
            gap_breakaway=factor_snapshot["gap_breakaway"],
            pattern_123_low_trendline=factor_snapshot["pattern_123_low_trendline"],
            is_limit_up=factor_snapshot["is_limit_up"],
            bottom_divergence_double_breakout=factor_snapshot["bottom_divergence_double_breakout"],
            theme_heat_score=theme.heat_score,
            leader_score=leader_score,
            volume_ratio=factor_snapshot["volume_ratio"],
            turnover_rate=factor_snapshot["turnover_rate"],
            circ_mv=factor_snapshot["circ_mv"],
            breakout_ratio=factor_snapshot["breakout_ratio"],
        )

        # Verify enrichment
        self.assertTrue(is_hot)
        self.assertGreater(theme_match_score, 0.8)
        self.assertGreater(leader_score, 50)
        self.assertGreaterEqual(extreme_strength_score, 75)

    def test_enrich_factor_snapshot_no_theme_match(self) -> None:
        """Test enriching factor snapshot with no theme match."""
        factor_snapshot = {
            "code": "000002",
            "name": "芯片股票",
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
            "trend_score": 70,
        }

        theme = ExternalTheme(
            name="机器人",
            heat_score=90.0,
            confidence=0.85,
            catalyst_summary="政策催化",
            keywords=["人形机器人"],
            evidence=[],
        )

        boards = ["芯片"]

        is_hot = self.theme_matcher.is_hot_theme_stock(
            boards=boards,
            stock_name=factor_snapshot["name"],
            theme_name=theme.name,
            keywords=theme.keywords,
        )

        self.assertFalse(is_hot)

    def test_enrich_factor_snapshot_below_strength_threshold(self) -> None:
        """Test enriching factor snapshot with score below 80."""
        factor_snapshot = {
            "code": "000003",
            "name": "机器人",
            "close": 10.5,
            "above_ma100": False,  # No base score
            "gap_breakaway": False,
            "pattern_123_low_trendline": False,
            "is_limit_up": False,
            "bottom_divergence_double_breakout": False,
            "volume_ratio": 0.8,
            "turnover_rate": 0.01,
            "circ_mv": 150_000_000_000,
            "breakout_ratio": 0.9,
            "trend_score": 30,
        }

        theme = ExternalTheme(
            name="机器人",
            heat_score=50.0,
            confidence=0.85,
            catalyst_summary="政策催化",
            keywords=["人形机器人"],
            evidence=[],
        )

        boards = ["机器人"]

        theme_match_score = self.theme_matcher.calculate_theme_match_score(
            boards=boards,
            stock_name=factor_snapshot["name"],
            theme_name=theme.name,
            keywords=theme.keywords,
        )

        leader_score = self.leader_calculator.calculate_leader_score(
            theme_match_score=theme_match_score,
            circ_mv=factor_snapshot["circ_mv"],
            turnover_rate=factor_snapshot["turnover_rate"],
            is_limit_up=factor_snapshot["is_limit_up"],
            gap_breakaway=factor_snapshot["gap_breakaway"],
            above_ma100=factor_snapshot["above_ma100"],
            ma100_breakout_days=0,
        )

        extreme_strength_score = self.strength_scorer.calculate_extreme_strength_score(
            above_ma100=factor_snapshot["above_ma100"],
            gap_breakaway=factor_snapshot["gap_breakaway"],
            pattern_123_low_trendline=factor_snapshot["pattern_123_low_trendline"],
            is_limit_up=factor_snapshot["is_limit_up"],
            bottom_divergence_double_breakout=factor_snapshot["bottom_divergence_double_breakout"],
            theme_heat_score=theme.heat_score,
            leader_score=leader_score,
            volume_ratio=factor_snapshot["volume_ratio"],
            turnover_rate=factor_snapshot["turnover_rate"],
            circ_mv=factor_snapshot["circ_mv"],
            breakout_ratio=factor_snapshot["breakout_ratio"],
        )

        is_selected = self.strength_scorer.is_selected(extreme_strength_score)
        is_watchlist = self.strength_scorer.is_watchlist(extreme_strength_score)

        self.assertFalse(is_selected)
        # May or may not be in watchlist depending on score


if __name__ == "__main__":
    unittest.main()
