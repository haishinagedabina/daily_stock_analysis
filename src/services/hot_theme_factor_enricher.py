# -*- coding: utf-8 -*-
"""Hot theme factor enrichment for FactorService."""

from typing import Dict, Any, List, Optional

from src.services.theme_matching_service import ThemeMatchingService
from src.services.leader_score_calculator import LeaderScoreCalculator
from src.services.extreme_strength_scorer import ExtremeStrengthScorer
from src.services.theme_context_ingest_service import OpenClawThemeContext
from src.services.core_signal_identifier import CoreSignalIdentifier


class HotThemeFactorEnricher:
    """Enrich factor snapshots with hot theme context."""

    def __init__(self) -> None:
        """Initialize enricher with scoring services."""
        self.theme_matcher = ThemeMatchingService()
        self.leader_calculator = LeaderScoreCalculator()
        self.strength_scorer = ExtremeStrengthScorer()
        self.signal_identifier = CoreSignalIdentifier()

    def enrich_snapshot(
        self,
        snapshot: Dict[str, Any],
        theme_context: Optional[OpenClawThemeContext],
        boards: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Enrich factor snapshot with hot theme fields.
        Returns enriched snapshot with theme-related fields.
        """
        if theme_context is None or not theme_context.themes:
            # No theme context, add default values
            snapshot["is_hot_theme_stock"] = False
            snapshot["primary_theme"] = None
            snapshot["theme_tags"] = []
            snapshot["theme_heat_score"] = 0.0
            snapshot["theme_match_score"] = 0.0
            snapshot["leader_score"] = 0
            snapshot["extreme_strength_score"] = 0.0
            snapshot["extreme_strength_reasons"] = []
            snapshot["entry_reason"] = None
            snapshot["core_signal"] = None
            snapshot["bonus_signals"] = []
            snapshot["theme_catalyst_summary"] = None
            snapshot["theme_catalyst_news"] = []
            snapshot["phase_results"] = {"phase1": False, "phase2": False, "phase3": False, "phase4": False, "phase5": False}
            snapshot["risk_params"] = {"stop_loss": 0, "position_size": "无", "take_profit_ratio": 0}
            return snapshot

        stock_name = snapshot.get("name", "")
        boards = boards or []

        # Find best matching theme
        best_theme = None
        best_match_score = 0.0
        best_theme_heat = 0.0

        for theme in theme_context.themes:
            match_score = self.theme_matcher.calculate_theme_match_score(
                boards=boards,
                stock_name=stock_name,
                theme_name=theme.name,
                keywords=theme.keywords,
            )
            if match_score > best_match_score:
                best_match_score = match_score
                best_theme = theme
                best_theme_heat = theme.heat_score

        # Check if hot theme stock
        is_hot = best_match_score >= self.theme_matcher.THEME_MATCH_THRESHOLD

        # Calculate leader score
        leader_score = 0
        if is_hot:
            leader_score = self.leader_calculator.calculate_leader_score(
                theme_match_score=best_match_score,
                circ_mv=snapshot.get("circ_mv", 0),
                turnover_rate=snapshot.get("turnover_rate", 0),
                is_limit_up=snapshot.get("is_limit_up", False),
                gap_breakaway=snapshot.get("gap_breakaway", False),
                above_ma100=snapshot.get("above_ma100", False),
                ma100_breakout_days=snapshot.get("ma100_breakout_days", 0),
            )

        # Calculate extreme strength score using corrected strategy
        extreme_strength_score = 0.0
        extreme_strength_reasons = []
        entry_reason = None
        core_signal = None
        bonus_signals = []

        if is_hot:
            # Identify core signal
            core_result = self.signal_identifier.identify_core_signal(
                has_gap=snapshot.get("gap_breakaway", False),
                has_limit_up=snapshot.get("is_limit_up", False),
                has_gap_breakout_ma100=snapshot.get("gap_breakaway", False) and snapshot.get("above_ma100", False),
            )

            # Identify bonus signals
            bonus_result = self.signal_identifier.identify_bonus_signals(
                has_low_123_breakout=snapshot.get("pattern_123_low_trendline", False),
                has_bottom_divergence=snapshot.get("bottom_divergence_double_breakout", False),
            )

            # Calculate total score
            extreme_strength_score = self.signal_identifier.calculate_total_score(
                core_result["core_signal_score"],
                bonus_result["bonus_score"],
            )

            core_signal = core_result["core_signal"]
            bonus_signals = bonus_result["bonus_signals"]
            extreme_strength_reasons = core_result["hit_reasons"] + bonus_result["hit_reasons"]

            # Determine entry reason (龙头选出原因)
            if snapshot.get("is_limit_up") and snapshot.get("intraday_minutes_since_open", 0) <= 30:
                entry_reason = "开盘半小时内涨停"
            elif snapshot.get("above_ma100"):
                entry_reason = "站上/刚突破MA100"

        # Build phase results
        phase_results = {
            "phase1": True,  # Market condition (checked at service level)
            "phase2": is_hot,  # Theme validation
            "phase3": is_hot and leader_score >= 50,  # Leader characteristics
            "phase4": is_hot and extreme_strength_score >= 60,  # Core signals
            "phase5": is_hot,  # Risk control applicable
        }

        # Build risk params
        risk_params = {
            "stop_loss": snapshot.get("ma100", 0) * 0.95 if snapshot.get("above_ma100") else 0,
            "position_size": "轻仓试错" if extreme_strength_score < 80 else "可加仓",
            "take_profit_ratio": 0.15 if extreme_strength_score >= 80 else 0.10,
        }

        # Extract news from theme evidence
        theme_catalyst_news = []
        if best_theme and best_theme.evidence:
            theme_catalyst_news = [
                {
                    "title": e.get("title", ""),
                    "source": e.get("source", ""),
                    "url": e.get("url"),
                    "published_at": e.get("published_at"),
                    "heat_score": best_theme_heat,
                }
                for e in best_theme.evidence
            ]

        # Enrich snapshot
        snapshot["is_hot_theme_stock"] = is_hot
        snapshot["primary_theme"] = best_theme.name if best_theme else None
        snapshot["theme_tags"] = [best_theme.name] if best_theme else []
        snapshot["theme_heat_score"] = best_theme_heat
        snapshot["theme_match_score"] = best_match_score
        snapshot["leader_score"] = leader_score
        snapshot["extreme_strength_score"] = extreme_strength_score
        snapshot["extreme_strength_reasons"] = extreme_strength_reasons
        snapshot["theme_catalyst_summary"] = best_theme.catalyst_summary if best_theme else None
        snapshot["theme_catalyst_news"] = theme_catalyst_news
        snapshot["entry_reason"] = entry_reason
        snapshot["core_signal"] = core_signal
        snapshot["bonus_signals"] = bonus_signals
        snapshot["phase_results"] = phase_results
        snapshot["risk_params"] = risk_params

        return snapshot
