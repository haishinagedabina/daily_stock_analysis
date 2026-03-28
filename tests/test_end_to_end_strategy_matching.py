# -*- coding: utf-8 -*-
"""TDD: Test end-to-end strategy matching in screening pipeline."""

import pytest
import pandas as pd
from src.services.screener_service import ScreenerService
from src.agent.skills.base import SkillManager


class TestEndToEndStrategyMatching:
    """Test that only requested strategies match candidates."""

    def test_extreme_strength_combo_only_matches_hot_theme_stocks(self):
        """RED: Only extreme_strength_combo should match when strategy_names=["extreme_strength_combo"]."""
        skill_manager = SkillManager()
        skill_manager.load_builtin_strategies()

        screener = ScreenerService(
            skill_manager=skill_manager,
            strategy_names=["extreme_strength_combo"]
        )

        # Create snapshot: hot theme stock with strong signals
        snapshot_df = pd.DataFrame([
            {
                "code": "301292",
                "name": "海科新源",
                "is_hot_theme_stock": True,
                "above_ma100": True,
                "is_limit_up": True,
                "gap_breakaway": False,
                "pattern_123_low_trendline": False,
                "extreme_strength_score": 85.0,
                "leader_score": 60,
                "theme_heat_score": 75.0,
                "is_st": False,
                "days_since_listed": 500,
                "avg_amount": 100_000_000,
            }
        ])

        result = screener.evaluate(snapshot_df)

        # Verify only extreme_strength_combo matched
        assert len(result.selected) > 0, "Should have selected candidates"
        for candidate in result.selected:
            assert candidate.matched_strategies == ["extreme_strength_combo"], \
                f"Expected only ['extreme_strength_combo'], got {candidate.matched_strategies}"

    def test_non_hot_theme_stock_rejected_by_extreme_strength_combo(self):
        """RED: Non-hot-theme stocks should be rejected by extreme_strength_combo."""
        skill_manager = SkillManager()
        skill_manager.load_builtin_strategies()

        screener = ScreenerService(
            skill_manager=skill_manager,
            strategy_names=["extreme_strength_combo"]
        )

        # Create snapshot: NOT a hot theme stock
        snapshot_df = pd.DataFrame([
            {
                "code": "600000",
                "name": "浦发银行",
                "is_hot_theme_stock": False,  # KEY: Not hot theme
                "above_ma100": True,
                "is_limit_up": True,
                "gap_breakaway": False,
                "pattern_123_low_trendline": False,
                "extreme_strength_score": 85.0,
                "leader_score": 60,
                "theme_heat_score": 0.0,
                "is_st": False,
                "days_since_listed": 5000,
                "avg_amount": 100_000_000,
            }
        ])

        result = screener.evaluate(snapshot_df)

        # Should be rejected
        assert len(result.selected) == 0, "Non-hot-theme stock should be rejected"
        assert len(result.rejected) > 0, "Should have rejection reasons"

    def test_multiple_strategies_when_no_filter(self):
        """RED: When strategy_names=None, multiple strategies can match same stock."""
        skill_manager = SkillManager()
        skill_manager.load_builtin_strategies()

        screener = ScreenerService(
            skill_manager=skill_manager,
            strategy_names=None  # No filter - use all strategies
        )

        # Create snapshot that could match multiple strategies
        snapshot_df = pd.DataFrame([
            {
                "code": "301292",
                "name": "海科新源",
                "is_hot_theme_stock": True,
                "above_ma100": True,
                "is_limit_up": True,
                "gap_breakaway": True,
                "pattern_123_low_trendline": True,
                "extreme_strength_score": 85.0,
                "leader_score": 60,
                "theme_heat_score": 75.0,
                "is_st": False,
                "days_since_listed": 500,
                "avg_amount": 100_000_000,
            }
        ])

        result = screener.evaluate(snapshot_df)

        # Can match multiple strategies
        if result.selected:
            for candidate in result.selected:
                # When no filter, multiple strategies can match
                assert len(candidate.matched_strategies) >= 1, \
                    f"Should have at least one matched strategy, got {candidate.matched_strategies}"
