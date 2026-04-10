from __future__ import annotations

from src.schemas.trading_types import SetupType


class SetupFreshnessAssessor:
    """统一评估 setup_freshness，输出 0.0~1.0。"""

    _BREAKOUT_DAY_KEYS = (
        "setup_freshness",
        "ma100_60min_freshness_score",
        "breakout_freshness_score",
        "entry_freshness_score",
        "ma100_breakout_days",
        "breakout_days",
        "days_since_breakout",
        "gap_breakout_days",
    )

    def assess(self, setup_type: SetupType, factor_snapshot: dict) -> float:
        if setup_type == SetupType.NONE:
            return 0.0

        for key in self._BREAKOUT_DAY_KEYS:
            raw = factor_snapshot.get(key)
            if raw is None:
                continue
            try:
                value = float(raw)
            except (TypeError, ValueError):
                continue
            if "freshness" in key:
                return max(0.0, min(value, 1.0))
            return self._score_from_breakout_days(value)

        if setup_type == SetupType.GAP_BREAKOUT and factor_snapshot.get("gap_breakaway"):
            return 0.9
        if setup_type == SetupType.LIMITUP_STRUCTURE and factor_snapshot.get("is_limit_up"):
            return 0.95
        if factor_snapshot.get("pattern_123_signal"):
            return 0.8
        if factor_snapshot.get("bottom_divergence_signal"):
            return 0.75
        return 0.5

    @staticmethod
    def _score_from_breakout_days(days: float) -> float:
        if days <= 0:
            return 0.0
        if days <= 1:
            return 1.0
        if days <= 2:
            return 0.9
        if days <= 3:
            return 0.8
        if days <= 5:
            return 0.7
        if days <= 8:
            return 0.5
        return 0.3
