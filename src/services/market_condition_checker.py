# -*- coding: utf-8 -*-
"""Market condition checker service."""

from typing import Dict, Any


class MarketConditionChecker:
    """Check market condition (informational only, not enforced)."""

    def check_market_condition(self, is_above_ma100: bool) -> Dict[str, Any]:
        """
        Check market condition based on MA100.

        Args:
            is_above_ma100: Whether market index is above MA100

        Returns:
            Dict with is_strong and message
        """
        if is_above_ma100:
            return {
                "is_strong": True,
                "message": "大盘强势（MA100之上）"
            }
        else:
            return {
                "is_strong": False,
                "message": "大盘弱势（MA100之下）"
            }
