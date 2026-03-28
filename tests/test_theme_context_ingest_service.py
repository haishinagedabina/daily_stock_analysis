# -*- coding: utf-8 -*-
"""Unit tests for ThemeContextIngestService."""

import unittest
from datetime import datetime
from typing import List, Dict, Any

from src.services.theme_context_ingest_service import (
    ThemeContextIngestService,
    ExternalTheme,
    OpenClawThemeContext,
)


class ExternalThemeTestCase(unittest.TestCase):
    """Test ExternalTheme data class."""

    def test_external_theme_creation(self) -> None:
        """Test creating ExternalTheme with valid data."""
        theme = ExternalTheme(
            name="机器人",
            heat_score=90.0,
            confidence=0.85,
            catalyst_summary="政策催化 + 产业事件驱动",
            keywords=["人形机器人", "丝杠", "减速器"],
            evidence=[
                {
                    "title": "示例新闻标题",
                    "source": "36kr",
                    "url": "https://example.com/news/1",
                    "published_at": "2026-03-26T08:20:00+08:00",
                }
            ],
        )
        self.assertEqual(theme.name, "机器人")
        self.assertEqual(theme.heat_score, 90.0)
        self.assertEqual(theme.confidence, 0.85)
        self.assertEqual(len(theme.keywords), 3)
        self.assertEqual(len(theme.evidence), 1)

    def test_external_theme_empty_keywords(self) -> None:
        """Test ExternalTheme with empty keywords."""
        theme = ExternalTheme(
            name="芯片",
            heat_score=75.0,
            confidence=0.80,
            catalyst_summary="产业升级",
            keywords=[],
            evidence=[],
        )
        self.assertEqual(len(theme.keywords), 0)


class ThemeContextIngestServiceTestCase(unittest.TestCase):
    """Test ThemeContextIngestService."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        self.service = ThemeContextIngestService()

    def test_validate_themes_empty(self) -> None:
        """Test validation fails with empty themes."""
        error = self.service.validate_themes([])
        self.assertIsNotNone(error)
        self.assertIn("empty", error.lower())

    def test_validate_themes_none(self) -> None:
        """Test validation fails with None themes."""
        error = self.service.validate_themes(None)
        self.assertIsNotNone(error)

    def test_validate_themes_valid(self) -> None:
        """Test validation passes with valid themes."""
        themes = [
            ExternalTheme(
                name="机器人",
                heat_score=90.0,
                confidence=0.85,
                catalyst_summary="政策催化",
                keywords=["人形机器人"],
                evidence=[],
            )
        ]
        error = self.service.validate_themes(themes)
        self.assertIsNone(error)

    def test_validate_theme_heat_score_range(self) -> None:
        """Test heat_score must be 0-100."""
        theme = ExternalTheme(
            name="芯片",
            heat_score=150.0,  # Invalid
            confidence=0.85,
            catalyst_summary="产业升级",
            keywords=["芯片"],
            evidence=[],
        )
        error = self.service.validate_theme(theme)
        self.assertIsNotNone(error)

    def test_validate_theme_confidence_range(self) -> None:
        """Test confidence must be 0-1."""
        theme = ExternalTheme(
            name="芯片",
            heat_score=75.0,
            confidence=1.5,  # Invalid
            catalyst_summary="产业升级",
            keywords=["芯片"],
            evidence=[],
        )
        error = self.service.validate_theme(theme)
        self.assertIsNotNone(error)

    def test_validate_theme_valid(self) -> None:
        """Test validation passes for valid theme."""
        theme = ExternalTheme(
            name="芯片",
            heat_score=75.0,
            confidence=0.85,
            catalyst_summary="产业升级",
            keywords=["芯片"],
            evidence=[],
        )
        error = self.service.validate_theme(theme)
        self.assertIsNone(error)

    def test_ingest_themes_valid(self) -> None:
        """Test ingesting valid themes."""
        themes = [
            ExternalTheme(
                name="机器人",
                heat_score=90.0,
                confidence=0.85,
                catalyst_summary="政策催化",
                keywords=["人形机器人"],
                evidence=[],
            )
        ]
        context = self.service.ingest_themes(
            trade_date="2026-03-26",
            market="cn",
            themes=themes,
        )
        self.assertIsNotNone(context)
        self.assertEqual(context.trade_date, "2026-03-26")
        self.assertEqual(context.market, "cn")
        self.assertEqual(len(context.themes), 1)

    def test_ingest_themes_invalid_market(self) -> None:
        """Test ingesting with invalid market."""
        themes = [
            ExternalTheme(
                name="机器人",
                heat_score=90.0,
                confidence=0.85,
                catalyst_summary="政策催化",
                keywords=["人形机器人"],
                evidence=[],
            )
        ]
        context = self.service.ingest_themes(
            trade_date="2026-03-26",
            market="us",  # Only cn supported in phase 1
            themes=themes,
        )
        self.assertIsNone(context)

    def test_ingest_themes_invalid_date_format(self) -> None:
        """Test ingesting with invalid date format."""
        themes = [
            ExternalTheme(
                name="机器人",
                heat_score=90.0,
                confidence=0.85,
                catalyst_summary="政策催化",
                keywords=["人形机器人"],
                evidence=[],
            )
        ]
        context = self.service.ingest_themes(
            trade_date="2026/03/26",  # Invalid format
            market="cn",
            themes=themes,
        )
        self.assertIsNone(context)


if __name__ == "__main__":
    unittest.main()
