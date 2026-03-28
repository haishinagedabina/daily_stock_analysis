# -*- coding: utf-8 -*-
"""Hot theme screening orchestrator service."""

from typing import Dict, Any, List, Optional
from datetime import date

from src.services.market_condition_checker import MarketConditionChecker
from src.services.leader_stock_selector import LeaderStockSelector
from src.services.core_signal_identifier import CoreSignalIdentifier
from src.services.theme_context_ingest_service import ExternalTheme


class HotThemeScreener:
    """Orchestrate hot theme stock screening logic."""

    def __init__(self):
        self.market_checker = MarketConditionChecker()
        self.leader_selector = LeaderStockSelector()
        self.signal_identifier = CoreSignalIdentifier()

    def screen_themes(
        self,
        themes: List[ExternalTheme],
        market_is_strong: bool = True,
        stock_signals: Dict[str, Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Screen hot theme stocks.

        Phase 1: Market check (informational) + theme lock
        Phase 2: Select 1 leader per theme by priority
        Phase 3: Identify core signals and calculate scores
        Phase 4-5: Not needed for screening

        Args:
            themes: List of ExternalTheme objects
            market_is_strong: Whether market is above MA100 (informational)
            stock_signals: Dict mapping stock_code to signal data
                {
                    "000001": {
                        "limit_up_within_30min": True,
                        "above_ma100": True,
                        "has_gap": True,
                        "has_limit_up": True,
                        "has_gap_breakout_ma100": False,
                        "has_low_123_breakout": True,
                        "has_bottom_divergence": False,
                    }
                }

        Returns:
            List of screening results, each with:
            - code, theme, theme_heat, theme_catalyst
            - entry_reason, core_signal, bonus_signals, total_score
            - hit_reasons, market_status
        """
        if stock_signals is None:
            stock_signals = {}

        results: List[Dict[str, Any]] = []

        # Phase 1: Market check (informational only)
        market_status = self.market_checker.check_market_condition(market_is_strong)

        # Process each theme
        for theme in themes:
            # Get theme stocks (mock: assume all stocks in keywords are candidates)
            theme_stocks = theme.keywords if theme.keywords else []

            if not theme_stocks:
                continue

            # Phase 2: Select leader by priority
            leader_code, entry_reason = self.leader_selector.select_leader(
                theme_stocks=theme_stocks,
                limit_up_within_30min=self._find_stock_by_condition(
                    theme_stocks, stock_signals, "limit_up_within_30min"
                ),
                above_ma100=self._find_stock_by_condition(
                    theme_stocks, stock_signals, "above_ma100"
                ),
            )

            if not leader_code:
                continue

            # Phase 3: Identify signals and calculate score
            stock_data = stock_signals.get(leader_code, {})

            core_result = self.signal_identifier.identify_core_signal(
                has_gap=stock_data.get("has_gap", False),
                has_limit_up=stock_data.get("has_limit_up", False),
                has_gap_breakout_ma100=stock_data.get("has_gap_breakout_ma100", False),
            )

            bonus_result = self.signal_identifier.identify_bonus_signals(
                has_low_123_breakout=stock_data.get("has_low_123_breakout", False),
                has_bottom_divergence=stock_data.get("has_bottom_divergence", False),
            )

            total_score = self.signal_identifier.calculate_total_score(
                core_result["core_signal_score"],
                bonus_result["bonus_score"],
            )

            # Filter by threshold (>= 80)
            if total_score < 80:
                continue

            # Combine hit reasons
            all_hit_reasons = core_result["hit_reasons"] + bonus_result["hit_reasons"]

            result = {
                "code": leader_code,
                "theme": theme.name,
                "theme_heat": theme.heat_score,
                "theme_catalyst": theme.catalyst_summary,
                "entry_reason": entry_reason,
                "core_signal": core_result["core_signal"],
                "bonus_signals": bonus_result["bonus_signals"],
                "total_score": total_score,
                "hit_reasons": all_hit_reasons,
                "market_status": market_status,
            }

            results.append(result)

        return results

    def _find_stock_by_condition(
        self,
        theme_stocks: List[str],
        stock_signals: Dict[str, Dict[str, Any]],
        condition_key: str,
    ) -> Optional[str]:
        """Find first stock in theme that matches condition."""
        for stock_code in theme_stocks:
            if stock_signals.get(stock_code, {}).get(condition_key, False):
                return stock_code
        return None
