# -*- coding: utf-8 -*-
"""Core signal identifier service for extreme strength screening."""

from typing import Dict, Any, List


# Core signal scores
CORE_SIGNAL_SCORES: Dict[str, int] = {
    "跳空涨停": 15,
    "缺口突破MA100": 12,
    "涨停": 10,
}

# Bonus signal scores
BONUS_SIGNAL_SCORES: Dict[str, int] = {
    "低位123结构": 12,
    "底背离双突破": 12,
}


class CoreSignalIdentifier:
    """Identify core technical signals and calculate scores."""

    def identify_core_signal(
        self,
        has_gap: bool = False,
        has_limit_up: bool = False,
        has_gap_breakout_ma100: bool = False,
    ) -> Dict[str, Any]:
        """
        Identify the strongest core signal.

        Priority: 跳空涨停 > 缺口突破MA100 > 涨停

        Args:
            has_gap: Whether stock has a gap up
            has_limit_up: Whether stock hit limit up
            has_gap_breakout_ma100: Whether stock has a gap breakout above MA100

        Returns:
            Dict with core_signal, core_signal_score, hit_reasons
        """
        hit_reasons: List[str] = []

        # Priority 1: Gap + Limit Up (strongest)
        if has_gap and has_limit_up:
            hit_reasons.append("跳空涨停（缺口+涨停共振）")
            return {
                "core_signal": "跳空涨停",
                "core_signal_score": CORE_SIGNAL_SCORES["跳空涨停"],
                "hit_reasons": hit_reasons,
            }

        # Priority 2: Gap breakout MA100
        if has_gap_breakout_ma100:
            hit_reasons.append("缺口突破MA100均线")
            return {
                "core_signal": "缺口突破MA100",
                "core_signal_score": CORE_SIGNAL_SCORES["缺口突破MA100"],
                "hit_reasons": hit_reasons,
            }

        # Priority 3: Limit up only
        if has_limit_up:
            hit_reasons.append("涨停")
            return {
                "core_signal": "涨停",
                "core_signal_score": CORE_SIGNAL_SCORES["涨停"],
                "hit_reasons": hit_reasons,
            }

        # No core signal
        return {
            "core_signal": None,
            "core_signal_score": 0,
            "hit_reasons": hit_reasons,
        }

    def identify_bonus_signals(
        self,
        has_low_123_breakout: bool = False,
        has_bottom_divergence: bool = False,
    ) -> Dict[str, Any]:
        """
        Identify bonus signals.

        Args:
            has_low_123_breakout: Whether stock shows low 123 structure breakout
            has_bottom_divergence: Whether stock shows bottom divergence double breakout

        Returns:
            Dict with bonus_signals, bonus_score, hit_reasons
        """
        bonus_signals: List[str] = []
        bonus_score = 0
        hit_reasons: List[str] = []

        if has_low_123_breakout:
            bonus_signals.append("低位123结构")
            bonus_score += BONUS_SIGNAL_SCORES["低位123结构"]
            hit_reasons.append("低位123结构+涨停突破高点2")

        if has_bottom_divergence:
            bonus_signals.append("底背离双突破")
            bonus_score += BONUS_SIGNAL_SCORES["底背离双突破"]
            hit_reasons.append("底背离双突破")

        return {
            "bonus_signals": bonus_signals,
            "bonus_score": bonus_score,
            "hit_reasons": hit_reasons,
        }

    def calculate_total_score(
        self,
        core_signal_score: int,
        bonus_score: int,
    ) -> int:
        """
        Calculate total score = core + bonus.

        Args:
            core_signal_score: Score from core signal
            bonus_score: Score from bonus signals

        Returns:
            Total score
        """
        return core_signal_score + bonus_score
