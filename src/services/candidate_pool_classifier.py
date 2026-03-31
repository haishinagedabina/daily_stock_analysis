# -*- coding: utf-8 -*-
"""
L3 候选池分级 — 静态优先级分层。

leader_pool: 龙头 + 主线题材，或极强个股 + 买点命中
focus_list:  中等强度，或买点命中 + 中等成熟度
watchlist:   其余
"""

from __future__ import annotations

from src.schemas.trading_types import CandidatePoolLevel, EntryMaturity, ThemePosition

LEADER_POOL_LEADER_SCORE = 70.0
LEADER_POOL_EXTREME_STRENGTH = 80.0
FOCUS_LIST_EXTREME_STRENGTH = 60.0


class CandidatePoolClassifier:

    def classify(
        self,
        leader_score: float,
        extreme_strength_score: float,
        theme_position: ThemePosition,
        entry_maturity: EntryMaturity,
        has_entry_core_hit: bool,
    ) -> CandidatePoolLevel:
        # leader_pool 路径 1: 龙头 + 主题
        if (leader_score >= LEADER_POOL_LEADER_SCORE
                and theme_position in (ThemePosition.MAIN_THEME, ThemePosition.SECONDARY_THEME)):
            return CandidatePoolLevel.LEADER_POOL

        # leader_pool 路径 2: 极强个股 + entry_core
        if extreme_strength_score >= LEADER_POOL_EXTREME_STRENGTH and has_entry_core_hit:
            return CandidatePoolLevel.LEADER_POOL

        # focus_list 路径 1: 中等强度
        if extreme_strength_score >= FOCUS_LIST_EXTREME_STRENGTH:
            return CandidatePoolLevel.FOCUS_LIST

        # focus_list 路径 2: entry_core + 中等成熟度
        if has_entry_core_hit and entry_maturity in (EntryMaturity.MEDIUM, EntryMaturity.HIGH):
            return CandidatePoolLevel.FOCUS_LIST

        return CandidatePoolLevel.WATCHLIST
