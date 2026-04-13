"""TDD tests for ScreeningTaskService strategy integration.

Tests that ScreeningTaskService can pass strategies through to ScreenerService
and that the _build_runtime_screener_service method creates strategy-aware instances.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.services.screening_mode_registry import ResolvedScreeningRuntimeConfig
from src.services.screening_task_service import ScreeningTaskService


def _make_runtime_config(**overrides) -> ResolvedScreeningRuntimeConfig:
    defaults = {
        "mode": "balanced",
        "candidate_limit": 30,
        "ai_top_k": 5,
        "min_list_days": 120,
        "min_volume_ratio": 1.2,
        "breakout_lookback_days": 20,
        "factor_lookback_days": 80,
    }
    defaults.update(overrides)
    return ResolvedScreeningRuntimeConfig(**defaults)


class TestScreeningTaskServiceStrategyIntegration:

    def test_build_runtime_screener_with_skill_manager(self):
        """When strategy_names are provided, _build_runtime_screener_service
        should pass the skill_manager and strategy_names through."""
        mock_db = MagicMock()
        mock_skill_mgr = MagicMock()

        service = ScreeningTaskService(
            db_manager=mock_db,
            skill_manager=mock_skill_mgr,
        )
        runtime_config = _make_runtime_config()
        screener = service._build_runtime_screener_service(
            runtime_config,
            strategy_names=["volume_breakout", "ma_golden_cross"],
        )

        assert screener._strategy_names == ["volume_breakout", "ma_golden_cross"]
        assert screener._skill_manager is mock_skill_mgr

    def test_build_runtime_screener_without_skill_manager(self):
        """Without skill_manager, ScreenerService should bootstrap builtin strategies."""
        mock_db = MagicMock()
        service = ScreeningTaskService(db_manager=mock_db)
        runtime_config = _make_runtime_config()
        screener = service._build_runtime_screener_service(runtime_config)

        assert screener._strategy_names is None
        assert screener._skill_manager is not None

    def test_resolve_active_strategies_default(self):
        """Default balanced mode returns all available strategies."""
        mock_db = MagicMock()
        mock_skill_mgr = MagicMock()
        mock_skill_mgr.get_screening_rules.return_value = [
            MagicMock(name="volume_breakout"),
            MagicMock(name="ma_golden_cross"),
            MagicMock(name="bottom_volume"),
        ]

        service = ScreeningTaskService(
            db_manager=mock_db,
            skill_manager=mock_skill_mgr,
        )

        strategies = service.resolve_active_strategies(mode="balanced")
        assert strategies is None  # None means "all available"

    def test_resolve_active_strategies_explicit(self):
        """Explicit strategy list is passed through."""
        mock_db = MagicMock()
        service = ScreeningTaskService(db_manager=mock_db)

        strategies = service.resolve_active_strategies(
            mode="balanced",
            strategies=["volume_breakout"],
        )
        assert strategies == ["volume_breakout"]


class TestScreeningAPISchemaStrategies:
    """Tests that the API schema accepts a strategies parameter."""

    def test_create_screening_run_request_accepts_strategies(self):
        from api.v1.schemas.screening import CreateScreeningRunRequest

        req = CreateScreeningRunRequest(strategies=["volume_breakout", "ma_golden_cross"])
        assert req.strategies == ["volume_breakout", "ma_golden_cross"]

    def test_create_screening_run_request_strategies_optional(self):
        from api.v1.schemas.screening import CreateScreeningRunRequest

        req = CreateScreeningRunRequest()
        assert req.strategies is None
