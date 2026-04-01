"""Tests for StrategyDispatcher — Phase 2B."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List, Optional

import pytest

from src.schemas.trading_types import MarketRegime
from src.services.strategy_dispatcher import DispatchResult, StrategyDispatcher


# ── Lightweight stub for StrategyScreeningRule ──────────────────────────────

@dataclass
class _StubRule:
    strategy_name: str
    system_role: Optional[str] = None
    strategy_family: Optional[str] = None
    applicable_market: Optional[List[str]] = None


def _make_rules() -> List[_StubRule]:
    """Return rules mirroring the real 12 strategy YAMLs."""
    return [
        _StubRule("bottom_divergence_double_breakout", "entry_core", "reversal", ["balanced", "aggressive"]),
        _StubRule("bottom_volume", "observation", "reversal", ["balanced", "aggressive", "defensive"]),
        _StubRule("bull_trend", "stock_pool", "trend", ["balanced", "aggressive", "defensive"]),
        _StubRule("dragon_head", "theme_score", "auxiliary", ["balanced", "aggressive"]),
        _StubRule("extreme_strength_combo", "stock_pool", "momentum", ["balanced", "aggressive"]),
        _StubRule("gap_limitup_breakout", "entry_core", "momentum", ["aggressive"]),
        _StubRule("ma100_60min_combined", "entry_core", "trend", ["balanced", "aggressive"]),
        _StubRule("ma100_low123_combined", "entry_core", "reversal", ["balanced", "aggressive"]),
        _StubRule("one_yang_three_yin", "bonus_signal", "auxiliary", ["balanced", "aggressive", "defensive"]),
        _StubRule("shrink_pullback", "entry_core", "trend", ["balanced", "aggressive"]),
        _StubRule("trendline_breakout", "confirm", "auxiliary", ["balanced", "aggressive"]),
        _StubRule("volume_breakout", "confirm", "auxiliary", ["balanced", "aggressive", "defensive"]),
    ]


@pytest.fixture()
def dispatcher() -> StrategyDispatcher:
    return StrategyDispatcher(_make_rules())


# ── Tests ──────────────────────────────────────────────────────────────────

class TestStandAside:
    def test_allows_only_observation(self, dispatcher: StrategyDispatcher):
        matched = [r.strategy_name for r in _make_rules()]
        result = dispatcher.filter_strategies(matched, MarketRegime.STAND_ASIDE)

        assert result.allowed_strategies == ["bottom_volume"]
        assert len(result.blocked_strategies) == 11

    def test_stand_aside_blocks_entry_core(self, dispatcher: StrategyDispatcher):
        result = dispatcher.filter_strategies(
            ["bottom_divergence_double_breakout", "ma100_60min_combined"],
            MarketRegime.STAND_ASIDE,
        )
        assert result.allowed_strategies == []
        assert set(result.blocked_strategies) == {
            "bottom_divergence_double_breakout", "ma100_60min_combined",
        }


class TestDefensive:
    def test_uses_applicable_market(self, dispatcher: StrategyDispatcher):
        matched = [r.strategy_name for r in _make_rules()]
        result = dispatcher.filter_strategies(matched, MarketRegime.DEFENSIVE)

        assert "bottom_volume" in result.allowed_strategies
        assert "bull_trend" in result.allowed_strategies
        assert "one_yang_three_yin" in result.allowed_strategies
        assert "volume_breakout" in result.allowed_strategies

        # These don't have "defensive" in applicable_market
        assert "bottom_divergence_double_breakout" in result.blocked_strategies
        assert "extreme_strength_combo" in result.blocked_strategies
        assert "gap_limitup_breakout" in result.blocked_strategies
        assert "ma100_60min_combined" in result.blocked_strategies

    def test_defensive_allows_4_blocks_8(self, dispatcher: StrategyDispatcher):
        matched = [r.strategy_name for r in _make_rules()]
        result = dispatcher.filter_strategies(matched, MarketRegime.DEFENSIVE)

        assert len(result.allowed_strategies) == 4
        assert len(result.blocked_strategies) == 8


class TestBalanced:
    def test_blocks_aggressive_only_strategies(self, dispatcher: StrategyDispatcher):
        matched = [r.strategy_name for r in _make_rules()]
        result = dispatcher.filter_strategies(matched, MarketRegime.BALANCED)

        # gap_limitup_breakout is aggressive-only
        assert "gap_limitup_breakout" in result.blocked_strategies
        assert len(result.blocked_strategies) == 1

    def test_allows_all_balanced_strategies(self, dispatcher: StrategyDispatcher):
        matched = [r.strategy_name for r in _make_rules()]
        result = dispatcher.filter_strategies(matched, MarketRegime.BALANCED)

        assert len(result.allowed_strategies) == 11


class TestAggressive:
    def test_allows_all(self, dispatcher: StrategyDispatcher):
        matched = [r.strategy_name for r in _make_rules()]
        result = dispatcher.filter_strategies(matched, MarketRegime.AGGRESSIVE)

        assert len(result.allowed_strategies) == 12
        assert len(result.blocked_strategies) == 0


class TestEdgeCases:
    def test_empty_matched_strategies(self, dispatcher: StrategyDispatcher):
        result = dispatcher.filter_strategies([], MarketRegime.AGGRESSIVE)

        assert result.allowed_strategies == []
        assert result.blocked_strategies == []
        assert "no_strategies" in result.reason

    def test_unknown_strategy_name_allowed(self, dispatcher: StrategyDispatcher):
        result = dispatcher.filter_strategies(
            ["unknown_strategy", "bottom_volume"],
            MarketRegime.STAND_ASIDE,
        )
        # Unknown strategy conservatively allowed
        assert "unknown_strategy" in result.allowed_strategies
        assert "bottom_volume" in result.allowed_strategies

    def test_dispatch_reason_readable(self, dispatcher: StrategyDispatcher):
        result = dispatcher.filter_strategies(
            ["gap_limitup_breakout", "bottom_volume"],
            MarketRegime.DEFENSIVE,
        )
        assert "regime=defensive" in result.reason
        assert "blocked=" in result.reason
        assert "gap_limitup_breakout" in result.reason


class TestPartialMatchedStrategies:
    """Test with only a subset of strategies matched (realistic scenario)."""

    def test_candidate_with_two_strategies(self, dispatcher: StrategyDispatcher):
        result = dispatcher.filter_strategies(
            ["ma100_60min_combined", "volume_breakout"],
            MarketRegime.BALANCED,
        )
        assert result.allowed_strategies == ["ma100_60min_combined", "volume_breakout"]
        assert result.blocked_strategies == []

    def test_all_strategies_blocked(self, dispatcher: StrategyDispatcher):
        result = dispatcher.filter_strategies(
            ["gap_limitup_breakout", "extreme_strength_combo"],
            MarketRegime.DEFENSIVE,
        )
        assert result.allowed_strategies == []
        assert len(result.blocked_strategies) == 2
