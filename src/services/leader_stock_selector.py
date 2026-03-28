# -*- coding: utf-8 -*-
"""Leader stock selector service with priority-based selection."""

from typing import Optional, Dict, Any


class LeaderStockSelector:
    """Select leader stock by priority."""

    def select_leader(
        self,
        theme_stocks: list[str],
        limit_up_within_30min: Optional[str] = None,
        above_ma100: Optional[str] = None
    ) -> tuple[Optional[str], Optional[str]]:
        """
        Select leader stock by priority.

        Priority 1: Limit up within 30 minutes of opening
        Priority 2: Above or just broke MA100
        Priority 3: None

        Args:
            theme_stocks: List of stock codes for the theme
            limit_up_within_30min: Stock code that hit limit up within 30min, or None
            above_ma100: Stock code that is above/broke MA100, or None

        Returns:
            Tuple of (leader_code, entry_reason) or (None, None)
        """
        # Priority 1: Limit up within 30 minutes
        if limit_up_within_30min and limit_up_within_30min in theme_stocks:
            return limit_up_within_30min, "开盘半小时内涨停"

        # Priority 2: Above or just broke MA100
        if above_ma100 and above_ma100 in theme_stocks:
            return above_ma100, "站上/刚突破MA100"

        # No match
        return None, None
