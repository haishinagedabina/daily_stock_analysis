# -*- coding: utf-8 -*-
"""
L3 候选池分级 — 静态优先级分层（纯 L3 概念，不依赖 L4 执行级字段）。

约束矩阵:
  MAIN_THEME / SECONDARY_THEME  → 可达 LEADER_POOL
  FOLLOWER_THEME                → 最高 FOCUS_LIST
  FADING_THEME / NON_THEME      → 固定 WATCHLIST
  stand_aside 环境              → 固定 WATCHLIST
"""

from __future__ import annotations

from typing import Optional

from src.schemas.trading_types import CandidatePoolLevel, MarketRegime, ThemePosition

LEADER_POOL_LEADER_SCORE = 70.0
LEADER_POOL_LEADER_SCORE_DEFENSIVE = 80.0
LEADER_POOL_EXTREME_STRENGTH = 80.0
FOCUS_LIST_EXTREME_STRENGTH = 60.0
FOCUS_LIST_LEADER_SCORE = 50.0

# Theme positions eligible for LEADER_POOL
_LEADER_ELIGIBLE_THEMES = frozenset({
    ThemePosition.MAIN_THEME,
    ThemePosition.SECONDARY_THEME,
})

# Theme positions hard-gated to WATCHLIST
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
    ) -> CandidatePoolLevel:
        # ── 1. 环境硬门控 ─────────────────────────────────────────────
        if market_regime == MarketRegime.STAND_ASIDE:
            return CandidatePoolLevel.WATCHLIST

        # ── 2. 题材硬门控：NON_THEME / FADING_THEME → WATCHLIST ──────
        if theme_position in _WATCHLIST_ONLY_THEMES:
            return CandidatePoolLevel.WATCHLIST

        # ── 3. defensive 模式提高 leader_pool 门槛 ───────────────────
        leader_threshold = (
            LEADER_POOL_LEADER_SCORE_DEFENSIVE
            if market_regime == MarketRegime.DEFENSIVE
            else LEADER_POOL_LEADER_SCORE
        )

        # ── 4. LEADER_POOL：必须在题材主线内 ─────────────────────────
        if theme_position in _LEADER_ELIGIBLE_THEMES:
            if leader_score >= leader_threshold:
                return CandidatePoolLevel.LEADER_POOL
            if extreme_strength_score >= LEADER_POOL_EXTREME_STRENGTH:
                return CandidatePoolLevel.LEADER_POOL

        # ── 5. FOCUS_LIST ─────────────────────────────────────────────
        if extreme_strength_score >= FOCUS_LIST_EXTREME_STRENGTH:
            return CandidatePoolLevel.FOCUS_LIST
        if leader_score >= FOCUS_LIST_LEADER_SCORE:
            return CandidatePoolLevel.FOCUS_LIST

        return CandidatePoolLevel.WATCHLIST
