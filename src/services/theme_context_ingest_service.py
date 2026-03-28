# -*- coding: utf-8 -*-
"""Theme context ingestion service for OpenClaw integration."""

from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional, Dict, Any


@dataclass
class ExternalTheme:
    """External theme from OpenClaw."""

    name: str
    heat_score: float
    confidence: float
    catalyst_summary: str
    keywords: List[str]
    evidence: List[Dict[str, Any]]


@dataclass
class OpenClawThemeContext:
    """Theme context for a screening run."""

    source: str
    trade_date: str
    market: str
    themes: List[ExternalTheme]
    accepted_at: str


class ThemeContextIngestService:
    """Service for ingesting and validating theme context from OpenClaw."""

    def validate_theme(self, theme: ExternalTheme) -> Optional[str]:
        """Validate a single theme. Returns error message if invalid, None if valid."""
        if not theme.name or not theme.name.strip():
            return "Theme name cannot be empty"

        if not isinstance(theme.heat_score, (int, float)):
            return "heat_score must be numeric"
        if not 0 <= theme.heat_score <= 100:
            return "heat_score must be between 0 and 100"

        if not isinstance(theme.confidence, (int, float)):
            return "confidence must be numeric"
        if not 0 <= theme.confidence <= 1:
            return "confidence must be between 0 and 1"

        if not theme.catalyst_summary or not theme.catalyst_summary.strip():
            return "catalyst_summary cannot be empty"

        if not isinstance(theme.keywords, list):
            return "keywords must be a list"

        if not isinstance(theme.evidence, list):
            return "evidence must be a list"

        return None

    def validate_themes(self, themes: Optional[List[ExternalTheme]]) -> Optional[str]:
        """Validate themes list. Returns error message if invalid, None if valid."""
        if themes is None:
            return "themes cannot be None"

        if not isinstance(themes, list):
            return "themes must be a list"

        if len(themes) == 0:
            return "themes cannot be empty"

        for theme in themes:
            error = self.validate_theme(theme)
            if error:
                return error

        return None

    def validate_trade_date(self, trade_date: str) -> Optional[str]:
        """Validate trade_date format (YYYY-MM-DD). Returns error if invalid."""
        try:
            datetime.strptime(trade_date, "%Y-%m-%d")
            return None
        except (ValueError, TypeError):
            return "trade_date must be in YYYY-MM-DD format"

    def ingest_themes(
        self,
        trade_date: str,
        market: str,
        themes: List[ExternalTheme],
    ) -> Optional[OpenClawThemeContext]:
        """
        Ingest themes from OpenClaw.
        Returns OpenClawThemeContext if valid, None if invalid.
        """
        # Validate market (phase 1 only supports cn)
        if market != "cn":
            return None

        # Validate trade_date format
        if self.validate_trade_date(trade_date):
            return None

        # Validate themes
        if self.validate_themes(themes):
            return None

        # Create context
        context = OpenClawThemeContext(
            source="openclaw",
            trade_date=trade_date,
            market=market,
            themes=themes,
            accepted_at=datetime.now().isoformat(),
        )

        return context
