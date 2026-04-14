# -*- coding: utf-8 -*-
"""
L3 candidate pool classification simplified for leader-stock workflow.

Rule:
- Only main/secondary theme limit-up stocks can enter leader_pool.
- Other stocks stay out of leader_pool regardless of legacy strength scores.
"""

from __future__ import annotations

from typing import Optional

from src.schemas.trading_types import CandidatePoolLevel, MarketRegime, ThemePosition

_LEADER_ELIGIBLE_THEMES = frozenset({
    ThemePosition.MAIN_THEME,
    ThemePosition.SECONDARY_THEME,
})

_WATCHLIST_ONLY_THEMES = frozenset({
    ThemePosition.NON_THEME,
    ThemePosition.FADING_THEME,
})


class CandidatePoolClassifier:

    def classify(
        self,
        leader_score: float,
        extreme_strength_score: float,
        theme_position: ThemePosition,
        market_regime: Optional[MarketRegime] = None,
        is_limit_up: bool = False,
    ) -> CandidatePoolLevel:
        del leader_score, extreme_strength_score

        if market_regime == MarketRegime.STAND_ASIDE:
            return CandidatePoolLevel.WATCHLIST

        if theme_position in _WATCHLIST_ONLY_THEMES:
            return CandidatePoolLevel.WATCHLIST

        if theme_position in _LEADER_ELIGIBLE_THEMES and is_limit_up:
            return CandidatePoolLevel.LEADER_POOL

        if theme_position == ThemePosition.FOLLOWER_THEME and is_limit_up:
            return CandidatePoolLevel.FOCUS_LIST

        if theme_position in _LEADER_ELIGIBLE_THEMES:
            return CandidatePoolLevel.FOCUS_LIST

        return CandidatePoolLevel.WATCHLIST
