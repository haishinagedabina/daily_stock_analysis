# -*- coding: utf-8 -*-
"""TDD: Test strategy_names filtering in ScreeningTaskService and SkillManager."""

import pytest
from unittest.mock import Mock, patch, MagicMock
from src.services.screening_task_service import ScreeningTaskService
from src.agent.skills.base import SkillManager


class TestStrategyNamesFiltering:
    """Test that strategy_names parameter correctly filters strategies."""

    def test_skill_manager_filters_by_strategy_names(self):
        """RED: SkillManager.get_screening_rules should only return requested strategies."""
        skill_manager = SkillManager()
        skill_manager.load_builtin_strategies()

        # Request only extreme_strength_combo
        rules = skill_manager.get_screening_rules(strategy_names=["extreme_strength_combo"])

        # All returned rules should be from extreme_strength_combo
        strategy_names = {rule.name for rule in rules}
        assert strategy_names == {"extreme_strength_combo"}, \
            f"Expected only extreme_strength_combo, got {strategy_names}"

    def test_skill_manager_returns_all_when_no_filter(self):
        """RED: SkillManager.get_screening_rules should return all when strategy_names is None."""
        skill_manager = SkillManager()
        skill_manager.load_builtin_strategies()

        rules = skill_manager.get_screening_rules(strategy_names=None)

        # Should have multiple strategies
        strategy_names = {rule.name for rule in rules}
        assert len(strategy_names) > 1, "Should return multiple strategies when no filter"

    def test_screening_task_service_passes_strategy_names_to_screener(self):
        """RED: ScreeningTaskService should pass strategy_names to ScreenerService."""
        service = ScreeningTaskService()
        service._active_strategy_names = ["extreme_strength_combo"]

        # Mock the screener service
        mock_screener = Mock()
        service.screener_service = mock_screener

        # Build runtime screener
        from src.services.screening_mode_registry import ResolvedScreeningRuntimeConfig
        runtime_config = ResolvedScreeningRuntimeConfig(
            mode="balanced",
            candidate_limit=50,
            ai_top_k=10,
            factor_lookback_days=120,
            breakout_lookback_days=20,
            min_list_days=120,
            min_volume_ratio=1.2,
            min_avg_amount=50_000_000,
        )

        screener = service._build_runtime_screener_service(
            runtime_config,
            strategy_names=service._active_strategy_names
        )

        # Verify strategy_names was passed
        assert screener._strategy_names == ["extreme_strength_combo"], \
            f"Expected strategy_names to be ['extreme_strength_combo'], got {screener._strategy_names}"

    def test_screener_service_filters_skills_by_strategy_names(self):
        """RED: ScreenerService should only use requested strategies."""
        from src.services.screener_service import ScreenerService
        import pandas as pd

        skill_manager = SkillManager()
        skill_manager.load_builtin_strategies()

        screener = ScreenerService(skill_manager=skill_manager, strategy_names=["extreme_strength_combo"])

        # Create minimal snapshot with hot theme stock
        snapshot_df = pd.DataFrame([
            {
                "code": "301292",
                "name": "海科新源",
                "is_hot_theme_stock": True,
                "above_ma100": True,
                "is_limit_up": False,
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
        if result.selected:
            for candidate in result.selected:
                assert "extreme_strength_combo" in candidate.matched_strategies, \
                    f"Expected extreme_strength_combo in matched_strategies, got {candidate.matched_strategies}"
