"""TDD tests for StrategyScreeningEngine.

Tests the generic rule evaluation engine that reads screening definitions
from Skill objects and evaluates factor snapshots.
"""
from __future__ import annotations

import pandas as pd
import pytest

from src.agent.skills.base import Skill
from src.services.strategy_screening_engine import (
    CommonFilterConfig,
    FilterCondition,
    MultiStrategyEvaluationResult,
    ScoringWeight,
    StrategyScreeningEngine,
    StrategyScreeningRule,
    build_rules_from_skills,
)


# ── Fixture helpers ──────────────────────────────────────────────────────────

def _make_rule(
    name: str = "test_strategy",
    display_name: str = "测试策略",
    category: str = "trend",
    filters: list | None = None,
    scoring: list | None = None,
) -> StrategyScreeningRule:
    return StrategyScreeningRule(
        strategy_name=name,
        display_name=display_name,
        category=category,
        filters=filters or [],
        scoring=scoring or [],
    )


def _make_snapshot(*rows) -> pd.DataFrame:
    return pd.DataFrame(rows)


def _bullish_row(code="600001", name="趋势龙头", **overrides):
    base = {
        "code": code,
        "name": name,
        "close": 10.4,
        "ma5": 10.2,
        "ma10": 10.0,
        "ma20": 9.8,
        "volume_ratio": 2.5,
        "avg_amount": 200_000_000,
        "breakout_ratio": 1.02,
        "pct_chg": 4.5,
        "is_st": False,
        "days_since_listed": 500,
        "trend_score": 85.0,
        "liquidity_score": 90.0,
    }
    base.update(overrides)
    return base


def _default_common_filters(**overrides):
    kwargs = {
        "exclude_st": True,
        "min_list_days": 120,
    }
    kwargs.update(overrides)
    return CommonFilterConfig(**kwargs)


# ── FilterCondition evaluation tests ─────────────────────────────────────────

class TestFilterConditionEvaluation:
    def test_gte_passes(self):
        fc = FilterCondition(field="volume_ratio", op=">=", value=2.0)
        row = {"volume_ratio": 2.5}
        assert StrategyScreeningEngine.evaluate_filter(fc, row) is True

    def test_gte_fails(self):
        fc = FilterCondition(field="volume_ratio", op=">=", value=2.0)
        row = {"volume_ratio": 1.5}
        assert StrategyScreeningEngine.evaluate_filter(fc, row) is False

    def test_lte(self):
        fc = FilterCondition(field="volume_ratio", op="<=", value=0.8)
        assert StrategyScreeningEngine.evaluate_filter(fc, {"volume_ratio": 0.6}) is True
        assert StrategyScreeningEngine.evaluate_filter(fc, {"volume_ratio": 1.2}) is False

    def test_gt_lt(self):
        fc_gt = FilterCondition(field="pct_chg", op=">", value=0)
        assert StrategyScreeningEngine.evaluate_filter(fc_gt, {"pct_chg": 0.5}) is True
        assert StrategyScreeningEngine.evaluate_filter(fc_gt, {"pct_chg": 0}) is False

        fc_lt = FilterCondition(field="pct_chg", op="<", value=0)
        assert StrategyScreeningEngine.evaluate_filter(fc_lt, {"pct_chg": -0.5}) is True

    def test_eq(self):
        fc = FilterCondition(field="is_st", op="==", value=False)
        assert StrategyScreeningEngine.evaluate_filter(fc, {"is_st": False}) is True
        assert StrategyScreeningEngine.evaluate_filter(fc, {"is_st": True}) is False

    def test_eq_string(self):
        fc = FilterCondition(field="candle_pattern", op="==", value="one_yang_three_yin")
        assert StrategyScreeningEngine.evaluate_filter(fc, {"candle_pattern": "one_yang_three_yin"}) is True
        assert StrategyScreeningEngine.evaluate_filter(fc, {"candle_pattern": "doji"}) is False

    def test_ne(self):
        fc = FilterCondition(field="is_st", op="!=", value=True)
        assert StrategyScreeningEngine.evaluate_filter(fc, {"is_st": False}) is True

    def test_value_ref_gte(self):
        fc = FilterCondition(field="ma5", op=">=", value_ref="ma10")
        assert StrategyScreeningEngine.evaluate_filter(fc, {"ma5": 10.5, "ma10": 10.0}) is True
        assert StrategyScreeningEngine.evaluate_filter(fc, {"ma5": 9.5, "ma10": 10.0}) is False

    def test_missing_field_returns_false(self):
        fc = FilterCondition(field="nonexistent", op=">=", value=1.0)
        assert StrategyScreeningEngine.evaluate_filter(fc, {"close": 10.0}) is False

    def test_none_field_returns_false(self):
        fc = FilterCondition(field="volume_ratio", op=">=", value=1.0)
        assert StrategyScreeningEngine.evaluate_filter(fc, {"volume_ratio": None}) is False


# ── ScoringWeight evaluation tests ──────────────────────────────────────────

class TestScoringWeightEvaluation:
    def test_basic_weight(self):
        sw = ScoringWeight(field="trend_score", weight=40)
        score = StrategyScreeningEngine.evaluate_score_component(sw, {"trend_score": 80.0})
        assert score == pytest.approx(40.0 * 80.0 / 100.0)

    def test_cap(self):
        sw = ScoringWeight(field="volume_ratio", weight=30, cap=3.0)
        score_capped = StrategyScreeningEngine.evaluate_score_component(sw, {"volume_ratio": 5.0})
        score_normal = StrategyScreeningEngine.evaluate_score_component(sw, {"volume_ratio": 2.0})
        assert score_capped == pytest.approx(30.0 * 3.0 / 3.0)
        assert score_normal == pytest.approx(30.0 * 2.0 / 3.0)

    def test_bonus_above(self):
        sw = ScoringWeight(
            field="breakout_ratio", weight=40, bonus_above=1.0, bonus_multiplier=1000
        )
        score = StrategyScreeningEngine.evaluate_score_component(sw, {"breakout_ratio": 1.03})
        # bonus = (1.03 - 1.0) * 1000 = 30.0; base_score is small; total should include bonus
        assert score >= 30.0

    def test_invert(self):
        sw = ScoringWeight(field="volume_ratio", weight=30, invert=True, cap=1.0)
        score_low = StrategyScreeningEngine.evaluate_score_component(sw, {"volume_ratio": 0.5})
        score_high = StrategyScreeningEngine.evaluate_score_component(sw, {"volume_ratio": 0.9})
        assert score_low > score_high

    def test_missing_field_returns_zero(self):
        sw = ScoringWeight(field="nonexistent", weight=40)
        assert StrategyScreeningEngine.evaluate_score_component(sw, {}) == 0.0


# ── Common filters tests ────────────────────────────────────────────────────

class TestCommonFilters:
    def test_st_filtered(self):
        engine = StrategyScreeningEngine()
        row = _bullish_row(is_st=True)
        reasons = engine.apply_common_filters(row, _default_common_filters())
        assert "st_filtered" in reasons

    def test_listing_days_filtered(self):
        engine = StrategyScreeningEngine()
        row = _bullish_row(days_since_listed=30)
        reasons = engine.apply_common_filters(row, _default_common_filters())
        assert "listed_days_below_threshold" in reasons

    def test_liquidity_no_longer_hard_filtered(self):
        engine = StrategyScreeningEngine()
        row = _bullish_row(avg_amount=10_000_000)
        reasons = engine.apply_common_filters(row, _default_common_filters())
        assert "liquidity_below_threshold" not in reasons

    def test_passes_all(self):
        engine = StrategyScreeningEngine()
        row = _bullish_row()
        reasons = engine.apply_common_filters(row, _default_common_filters())
        assert reasons == []

    def test_big_drop_is_filtered(self):
        engine = StrategyScreeningEngine()
        row = _bullish_row(pct_chg=-9.88, close_strength=0.0, candle_pattern="big_yin")
        reasons = engine.apply_common_filters(row, _default_common_filters())
        assert "big_drop_filtered" in reasons
        assert "weak_close_filtered" in reasons
        assert "big_yin_candle_filtered" in reasons

    def test_recent_bottom_divergence_weak_close_is_not_filtered(self):
        engine = StrategyScreeningEngine()
        row = _bullish_row(
            pct_chg=-1.5,
            close_strength=0.0,
            candle_pattern="normal",
            bottom_divergence_double_breakout=True,
            bottom_divergence_confirmation_days=3,
        )
        reasons = engine.apply_common_filters(row, _default_common_filters())
        assert "weak_close_filtered" not in reasons

    def test_same_day_bottom_divergence_weak_close_is_not_filtered(self):
        engine = StrategyScreeningEngine()
        row = _bullish_row(
            pct_chg=-1.0,
            close_strength=0.0,
            candle_pattern="normal",
            bottom_divergence_double_breakout=True,
            bottom_divergence_confirmation_days=0,
        )
        reasons = engine.apply_common_filters(row, _default_common_filters())
        assert "weak_close_filtered" not in reasons


# ── Multi-strategy evaluate tests ───────────────────────────────────────────

class TestMultiStrategyEvaluation:
    def test_single_strategy_selects_matching_rows(self):
        rule = _make_rule(
            filters=[
                FilterCondition(field="volume_ratio", op=">=", value=2.0),
                FilterCondition(field="breakout_ratio", op=">=", value=0.995),
            ],
            scoring=[
                ScoringWeight(field="trend_score", weight=50),
                ScoringWeight(field="volume_ratio", weight=50, cap=5.0),
            ],
        )
        snapshot = _make_snapshot(
            _bullish_row("600001", volume_ratio=2.5, breakout_ratio=1.02),
            _bullish_row("600002", volume_ratio=1.0, breakout_ratio=0.99),
        )
        engine = StrategyScreeningEngine()
        result = engine.evaluate(
            snapshot_df=snapshot,
            rules=[rule],
            common_filters=_default_common_filters(),
        )

        assert isinstance(result, MultiStrategyEvaluationResult)
        selected_codes = [c.code for c in result.selected]
        assert "600001" in selected_codes
        assert "600002" not in selected_codes

    def test_low_liquidity_row_can_still_enter_strategy_matching(self):
        rule = _make_rule(
            filters=[
                FilterCondition(field="volume_ratio", op=">=", value=2.0),
                FilterCondition(field="breakout_ratio", op=">=", value=0.995),
            ],
            scoring=[
                ScoringWeight(field="trend_score", weight=50),
                ScoringWeight(field="volume_ratio", weight=50, cap=5.0),
            ],
        )
        snapshot = _make_snapshot(
            _bullish_row("600003", volume_ratio=2.5, breakout_ratio=1.02, avg_amount=10_000_000),
        )
        engine = StrategyScreeningEngine()
        result = engine.evaluate(
            snapshot_df=snapshot,
            rules=[rule],
            common_filters=_default_common_filters(),
        )

        assert [c.code for c in result.selected] == ["600003"]
        assert result.rejected == []

    def test_multi_strategy_union_candidates(self):
        """Two strategies, each matching different stocks."""
        rule_breakout = _make_rule(
            name="breakout",
            filters=[FilterCondition(field="breakout_ratio", op=">=", value=1.0)],
            scoring=[ScoringWeight(field="breakout_ratio", weight=100)],
        )
        rule_volume = _make_rule(
            name="volume",
            filters=[FilterCondition(field="volume_ratio", op=">=", value=3.0)],
            scoring=[ScoringWeight(field="volume_ratio", weight=100, cap=5.0)],
        )
        snapshot = _make_snapshot(
            _bullish_row("600001", breakout_ratio=1.05, volume_ratio=1.5),
            _bullish_row("600002", breakout_ratio=0.95, volume_ratio=4.0),
        )
        engine = StrategyScreeningEngine()
        result = engine.evaluate(
            snapshot_df=snapshot,
            rules=[rule_breakout, rule_volume],
            common_filters=_default_common_filters(),
        )

        selected_codes = {c.code for c in result.selected}
        assert "600001" in selected_codes
        assert "600002" in selected_codes

    def test_candidate_has_matched_strategies(self):
        rule_a = _make_rule(
            name="strategy_a",
            filters=[FilterCondition(field="volume_ratio", op=">=", value=2.0)],
            scoring=[ScoringWeight(field="volume_ratio", weight=100, cap=5.0)],
        )
        rule_b = _make_rule(
            name="strategy_b",
            filters=[FilterCondition(field="trend_score", op=">=", value=80)],
            scoring=[ScoringWeight(field="trend_score", weight=100)],
        )
        snapshot = _make_snapshot(
            _bullish_row("600001", volume_ratio=2.5, trend_score=85),
        )
        engine = StrategyScreeningEngine()
        result = engine.evaluate(
            snapshot_df=snapshot,
            rules=[rule_a, rule_b],
            common_filters=_default_common_filters(),
        )

        assert len(result.selected) == 1
        assert set(result.selected[0].matched_strategies) == {"strategy_a", "strategy_b"}

    def test_strategy_stats_populated(self):
        rule = _make_rule(
            name="my_strategy",
            filters=[FilterCondition(field="volume_ratio", op=">=", value=1.0)],
            scoring=[ScoringWeight(field="volume_ratio", weight=100, cap=5.0)],
        )
        snapshot = _make_snapshot(
            _bullish_row("600001"),
            _bullish_row("600002"),
        )
        engine = StrategyScreeningEngine()
        result = engine.evaluate(
            snapshot_df=snapshot,
            rules=[rule],
            common_filters=_default_common_filters(),
        )

        assert result.strategy_stats["my_strategy"] == 2

    def test_candidates_sorted_by_score_descending(self):
        rule = _make_rule(
            filters=[],
            scoring=[ScoringWeight(field="trend_score", weight=100)],
        )
        snapshot = _make_snapshot(
            _bullish_row("600001", trend_score=50),
            _bullish_row("600002", trend_score=90),
            _bullish_row("600003", trend_score=70),
        )
        engine = StrategyScreeningEngine()
        result = engine.evaluate(
            snapshot_df=snapshot,
            rules=[rule],
            common_filters=_default_common_filters(),
        )

        codes = [c.code for c in result.selected]
        assert codes == ["600002", "600003", "600001"]

    def test_candidate_limit(self):
        rule = _make_rule(
            filters=[],
            scoring=[ScoringWeight(field="trend_score", weight=100)],
        )
        snapshot = _make_snapshot(
            *[_bullish_row(f"60000{i}", trend_score=80 - i) for i in range(10)]
        )
        engine = StrategyScreeningEngine()
        result = engine.evaluate(
            snapshot_df=snapshot,
            rules=[rule],
            common_filters=_default_common_filters(),
            candidate_limit=3,
        )

        assert len(result.selected) == 3

    def test_rank_assigned_correctly(self):
        rule = _make_rule(
            filters=[],
            scoring=[ScoringWeight(field="trend_score", weight=100)],
        )
        snapshot = _make_snapshot(
            _bullish_row("600001", trend_score=50),
            _bullish_row("600002", trend_score=90),
        )
        engine = StrategyScreeningEngine()
        result = engine.evaluate(
            snapshot_df=snapshot,
            rules=[rule],
            common_filters=_default_common_filters(),
        )

        assert result.selected[0].rank == 1
        assert result.selected[0].code == "600002"
        assert result.selected[1].rank == 2

    def test_empty_snapshot_returns_empty(self):
        engine = StrategyScreeningEngine()
        result = engine.evaluate(
            snapshot_df=pd.DataFrame(),
            rules=[_make_rule()],
            common_filters=_default_common_filters(),
        )
        assert result.selected == []
        assert result.rejected == []

    def test_rejected_includes_reasons(self):
        rule = _make_rule(
            filters=[FilterCondition(field="volume_ratio", op=">=", value=10.0)],
            scoring=[ScoringWeight(field="volume_ratio", weight=100, cap=10.0)],
        )
        snapshot = _make_snapshot(_bullish_row("600001", volume_ratio=2.0))
        engine = StrategyScreeningEngine()
        result = engine.evaluate(
            snapshot_df=snapshot,
            rules=[rule],
            common_filters=_default_common_filters(),
        )

        assert len(result.selected) == 0
        assert len(result.rejected) == 1
        assert result.rejected[0]["code"] == "600001"


# ── score aggregation tests ─────────────────────────────────────────────────

class TestScoreAggregation:
    def test_multi_strategy_score_uses_role_weights(self):
        """Aggregation: role-weighted sum across matched strategies."""
        rule_a = _make_rule(
            name="weak",
            filters=[],
            scoring=[ScoringWeight(field="trend_score", weight=10)],
        )
        rule_a.system_role = "confirm"
        rule_b = _make_rule(
            name="strong",
            filters=[],
            scoring=[ScoringWeight(field="trend_score", weight=100)],
        )
        rule_b.system_role = "entry_core"
        snapshot = _make_snapshot(_bullish_row("600001", trend_score=80))
        engine = StrategyScreeningEngine()
        result = engine.evaluate(
            snapshot_df=snapshot,
            rules=[rule_a, rule_b],
            common_filters=_default_common_filters(),
        )

        candidate = result.selected[0]
        assert candidate.strategy_scores["strong"] > candidate.strategy_scores["weak"]
        expected = (
            candidate.strategy_scores["strong"] * 1.0
            + candidate.strategy_scores["weak"] * 0.5
        )
        assert candidate.final_score == pytest.approx(expected)

    def test_dual_strategy_stock_ranks_higher_than_single(self):
        """Stock matching 2 strategies should score higher than single-match."""
        rule_a = _make_rule(
            name="strategy_a",
            filters=[FilterCondition(field="volume_ratio", op=">=", value=2.0)],
            scoring=[ScoringWeight(field="trend_score", weight=50)],
        )
        rule_a.system_role = "entry_core"
        rule_b = _make_rule(
            name="strategy_b",
            filters=[FilterCondition(field="trend_score", op=">=", value=80)],
            scoring=[ScoringWeight(field="trend_score", weight=50)],
        )
        rule_b.system_role = "entry_core"
        snapshot = _make_snapshot(
            _bullish_row("600001", volume_ratio=2.5, trend_score=85),  # matches both
            _bullish_row("600002", volume_ratio=1.0, trend_score=90),  # matches only B
        )
        engine = StrategyScreeningEngine()
        result = engine.evaluate(
            snapshot_df=snapshot,
            rules=[rule_a, rule_b],
            common_filters=_default_common_filters(),
        )

        codes = [c.code for c in result.selected]
        assert codes[0] == "600001", "dual-match stock should rank first"
        dual = result.selected[0]
        assert len(dual.matched_strategies) == 2
        assert dual.final_score == pytest.approx(sum(dual.strategy_scores.values()))

    def test_strategy_score_is_capped_at_100(self):
        rule = _make_rule(
            scoring=[
                ScoringWeight(field="trend_score", weight=80),
                ScoringWeight(field="volume_ratio", weight=60, cap=5.0),
            ],
        )
        engine = StrategyScreeningEngine()

        score = engine._compute_strategy_score(rule, _bullish_row(trend_score=100, volume_ratio=5.0))

        assert score == 100.0


class TestNestedFilterGroups:
    def test_build_rules_from_skills_enforces_any_group(self):
        skill = Skill(
            name="extreme_strength_combo",
            display_name="极端强势组合",
            description="热点题材硬门槛下的强势信号聚合策略",
            instructions="",
            category="momentum",
            screening={
                "filters": [
                    {"field": "is_hot_theme_stock", "op": "==", "value": True},
                    {
                        "any": [
                            {"field": "above_ma100", "op": "==", "value": True},
                            {"field": "gap_breakaway", "op": "==", "value": True},
                            {"field": "is_limit_up", "op": "==", "value": True},
                        ]
                    },
                ],
                "scoring": [
                    {"field": "extreme_strength_score", "weight": 100},
                ],
            },
        )
        rules = build_rules_from_skills([skill])
        engine = StrategyScreeningEngine()

        snapshot = _make_snapshot(
            _bullish_row(
                "600001",
                is_hot_theme_stock=True,
                above_ma100=False,
                gap_breakaway=False,
                is_limit_up=False,
                extreme_strength_score=85,
            ),
            _bullish_row(
                "600002",
                is_hot_theme_stock=True,
                above_ma100=False,
                gap_breakaway=True,
                is_limit_up=False,
                extreme_strength_score=88,
            ),
        )

        result = engine.evaluate(
            snapshot_df=snapshot,
            rules=rules,
            common_filters=_default_common_filters(),
        )

        selected_codes = [item.code for item in result.selected]
        assert selected_codes == ["600002"]

    def test_build_rules_from_skills_supports_legacy_or_syntax(self):
        skill = Skill(
            name="gap_limitup_breakout",
            display_name="跳空涨停突破",
            description="legacy or syntax",
            instructions="",
            category="momentum",
            screening={
                "filters": [
                    {"field": "above_ma100", "op": "==", "value": True},
                    {
                        "field": "gap_breakaway",
                        "op": "==",
                        "value": True,
                        "or": [
                            {"field": "limit_up_breakout", "op": "==", "value": True},
                        ],
                    },
                ],
                "scoring": [{"field": "trend_score", "weight": 100}],
            },
        )

        rules = build_rules_from_skills([skill])
        engine = StrategyScreeningEngine()
        snapshot = _make_snapshot(
            _bullish_row("600001", above_ma100=True, gap_breakaway=False, limit_up_breakout=True),
            _bullish_row("600002", above_ma100=True, gap_breakaway=False, limit_up_breakout=False),
        )

        result = engine.evaluate(
            snapshot_df=snapshot,
            rules=rules,
            common_filters=_default_common_filters(),
        )

        selected_codes = [item.code for item in result.selected]
        assert selected_codes == ["600001"]
