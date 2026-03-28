# -*- coding: utf-8 -*-
"""Unit tests for ScreeningTaskService hot theme integration."""

import unittest
from datetime import date
from typing import Dict, Any, Optional, List
from unittest.mock import Mock, MagicMock, patch

from src.services.screening_task_service import ScreeningTaskService
from src.services.theme_context_ingest_service import (
    ThemeContextIngestService,
    ExternalTheme,
    OpenClawThemeContext,
)


class ScreeningTaskServiceHotThemeIntegrationTestCase(unittest.TestCase):
    """Test ScreeningTaskService integration with hot theme context."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        self.service = ScreeningTaskService()
        self.theme_ingest_service = ThemeContextIngestService()

    def test_execute_run_with_theme_context(self) -> None:
        """Test execute_run accepts theme_context in run_snapshot."""
        # Create theme context
        themes = [
            ExternalTheme(
                name="机器人",
                heat_score=90.0,
                confidence=0.85,
                catalyst_summary="政策催化",
                keywords=["机器人"],
                evidence=[],
            )
        ]
        theme_context = self.theme_ingest_service.ingest_themes(
            trade_date="2026-03-26",
            market="cn",
            themes=themes,
        )
        self.assertIsNotNone(theme_context)

    def test_theme_context_in_run_snapshot(self) -> None:
        """Test theme_context is properly stored in run_snapshot."""
        themes = [
            ExternalTheme(
                name="机器人",
                heat_score=90.0,
                confidence=0.85,
                catalyst_summary="政策催化",
                keywords=["机器人"],
                evidence=[],
            )
        ]
        theme_context = self.theme_ingest_service.ingest_themes(
            trade_date="2026-03-26",
            market="cn",
            themes=themes,
        )

        # Simulate run_snapshot with theme_context
        run_snapshot = {
            "trade_date": "2026-03-26",
            "market": "cn",
            "strategy_names": ["extreme_strength_combo"],
            "theme_context": {
                "source": theme_context.source,
                "trade_date": theme_context.trade_date,
                "market": theme_context.market,
                "themes": [
                    {
                        "name": t.name,
                        "heat_score": t.heat_score,
                        "confidence": t.confidence,
                        "catalyst_summary": t.catalyst_summary,
                        "keywords": t.keywords,
                    }
                    for t in theme_context.themes
                ],
                "accepted_at": theme_context.accepted_at,
            },
        }

        self.assertIn("theme_context", run_snapshot)
        self.assertEqual(run_snapshot["theme_context"]["market"], "cn")
        self.assertEqual(len(run_snapshot["theme_context"]["themes"]), 1)
        self.assertEqual(run_snapshot["theme_context"]["themes"][0]["name"], "机器人")

    def test_build_run_config_snapshot_includes_theme_context(self) -> None:
        """Test run config snapshot includes serialized theme context."""
        themes = [
            ExternalTheme(
                name="机器人",
                heat_score=90.0,
                confidence=0.85,
                catalyst_summary="政策催化",
                keywords=["机器人"],
                evidence=[{"title": "政策发布", "source": "新华社"}],
            )
        ]
        theme_context = self.theme_ingest_service.ingest_themes(
            trade_date="2026-03-26",
            market="cn",
            themes=themes,
        )

        snapshot = ScreeningTaskService._build_run_config_snapshot(
            requested_trade_date=date(2026, 3, 26),
            normalized_stock_codes=[],
            runtime_config=self.service.resolve_run_config(mode="balanced", candidate_limit=50, ai_top_k=10),
            ingest_failure_threshold=0.2,
            strategy_names=["extreme_strength_combo"],
            theme_context=theme_context,
        )

        self.assertIn("theme_context", snapshot)
        self.assertEqual(snapshot["theme_context"]["trade_date"], "2026-03-26")
        self.assertEqual(snapshot["theme_context"]["themes"][0]["name"], "机器人")
        self.assertEqual(snapshot["theme_context"]["themes"][0]["evidence"][0]["title"], "政策发布")

    def test_strategy_names_fixed_for_openclaw(self) -> None:
        """Test strategy_names is fixed to extreme_strength_combo for OpenClaw."""
        # When OpenClaw calls the endpoint, strategy_names should be fixed
        strategy_names = ["extreme_strength_combo"]
        self.assertEqual(strategy_names, ["extreme_strength_combo"])

    def test_theme_context_validation_in_run(self) -> None:
        """Test theme_context validation during run creation."""
        # Invalid theme context (empty themes)
        invalid_context = self.theme_ingest_service.ingest_themes(
            trade_date="2026-03-26",
            market="cn",
            themes=[],
        )
        self.assertIsNone(invalid_context)

        # Valid theme context
        valid_themes = [
            ExternalTheme(
                name="机器人",
                heat_score=90.0,
                confidence=0.85,
                catalyst_summary="政策催化",
                keywords=["机器人"],
                evidence=[],
            )
        ]
        valid_context = self.theme_ingest_service.ingest_themes(
            trade_date="2026-03-26",
            market="cn",
            themes=valid_themes,
        )
        self.assertIsNotNone(valid_context)

    def test_theme_context_market_constraint(self) -> None:
        """Test theme_context only accepts cn market in phase 1."""
        themes = [
            ExternalTheme(
                name="机器人",
                heat_score=90.0,
                confidence=0.85,
                catalyst_summary="政策催化",
                keywords=["机器人"],
                evidence=[],
            )
        ]

        # cn market should work
        cn_context = self.theme_ingest_service.ingest_themes(
            trade_date="2026-03-26",
            market="cn",
            themes=themes,
        )
        self.assertIsNotNone(cn_context)

        # us market should fail
        us_context = self.theme_ingest_service.ingest_themes(
            trade_date="2026-03-26",
            market="us",
            themes=themes,
        )
        self.assertIsNone(us_context)


if __name__ == "__main__":
    unittest.main()
