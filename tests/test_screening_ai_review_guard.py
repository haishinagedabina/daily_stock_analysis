from __future__ import annotations

from src.schemas.screening_ai_review import (
    ScreeningAiReviewResult,
    build_rules_fallback_review,
)
from src.schemas.trading_types import CandidateDecision, EntryMaturity, SetupType, TradeStage
from src.services.screening_ai_review_guard import ScreeningAiReviewGuard


def _make_candidate(**overrides):
    base = CandidateDecision(code="600519", name="贵州茅台", trade_stage=TradeStage.FOCUS)
    for key, value in overrides.items():
        setattr(base, key, value)
    return base


def test_screening_ai_review_result_exposes_contract_fields() -> None:
    review = ScreeningAiReviewResult(
        environment_ok=True,
        trade_stage=TradeStage.FOCUS,
        entry_maturity=EntryMaturity.MEDIUM,
        setup_type=SetupType.TREND_BREAKOUT,
        risk_level="medium",
        initial_position="1/4",
        stop_loss_rule="跌破MA20离场",
        take_profit_plan="沿5日线止盈",
        invalidation_rule="放量长阴失效",
        reasoning_summary="结构仍完整",
        confidence=0.72,
        result_source="rules_plus_ai",
        is_fallback=False,
        fallback_reason=None,
    )

    payload = review.to_payload()

    assert payload["environment_ok"] is True
    assert payload["trade_stage"] == "focus"
    assert payload["entry_maturity"] == "medium"
    assert payload["setup_type"] == "trend_breakout"
    assert payload["risk_level"] == "medium"
    assert payload["initial_position"] == "1/4"
    assert payload["stop_loss_rule"] == "跌破MA20离场"
    assert payload["take_profit_plan"] == "沿5日线止盈"
    assert payload["invalidation_rule"] == "放量长阴失效"
    assert payload["reasoning_summary"] == "结构仍完整"
    assert payload["confidence"] == 0.72
    assert payload["fallback_reason"] is None
    assert payload["result_source"] == "rules_plus_ai"


def test_guard_caps_trade_stage_when_environment_is_not_ok() -> None:
    candidate = _make_candidate(trade_stage=TradeStage.ADD_ON_STRENGTH)
    review = ScreeningAiReviewResult(
        environment_ok=False,
        trade_stage=TradeStage.ADD_ON_STRENGTH,
        entry_maturity=EntryMaturity.HIGH,
        setup_type=SetupType.TREND_BREAKOUT,
        risk_level="high",
        initial_position="1/4",
        stop_loss_rule="跌破MA20离场",
        take_profit_plan="沿5日线止盈",
        invalidation_rule="放量长阴失效",
        reasoning_summary="环境一般",
        confidence=0.82,
        result_source="rules_plus_ai",
        is_fallback=False,
        fallback_reason=None,
    )

    guarded = ScreeningAiReviewGuard().apply(candidate, review)

    assert guarded.trade_stage == TradeStage.WATCH
    assert "environment_constraint" in guarded.downgrade_reasons


def test_guard_blocks_high_entry_maturity_when_setup_is_none() -> None:
    candidate = _make_candidate(setup_type=SetupType.NONE)
    review = ScreeningAiReviewResult(
        environment_ok=True,
        trade_stage=TradeStage.FOCUS,
        entry_maturity=EntryMaturity.HIGH,
        setup_type=SetupType.NONE,
        risk_level="medium",
        initial_position=None,
        stop_loss_rule=None,
        take_profit_plan=None,
        invalidation_rule=None,
        reasoning_summary="暂无明确形态",
        confidence=0.55,
        result_source="rules_plus_ai",
        is_fallback=False,
        fallback_reason=None,
    )

    guarded = ScreeningAiReviewGuard().apply(candidate, review)

    assert guarded.entry_maturity != EntryMaturity.HIGH
    assert "setup_constraint" in guarded.downgrade_reasons


def test_guard_downgrades_execution_stage_when_plan_fields_are_missing() -> None:
    candidate = _make_candidate(trade_stage=TradeStage.PROBE_ENTRY)
    review = ScreeningAiReviewResult(
        environment_ok=True,
        trade_stage=TradeStage.PROBE_ENTRY,
        entry_maturity=EntryMaturity.HIGH,
        setup_type=SetupType.TREND_BREAKOUT,
        risk_level="medium",
        initial_position="1/4",
        stop_loss_rule="",
        take_profit_plan="沿5日线止盈",
        invalidation_rule="放量长阴失效",
        reasoning_summary="计划不完整",
        confidence=0.7,
        result_source="rules_plus_ai",
        is_fallback=False,
        fallback_reason=None,
    )

    guarded = ScreeningAiReviewGuard().apply(candidate, review)

    assert guarded.trade_stage == TradeStage.FOCUS
    assert "missing_stop_anchor" in guarded.downgrade_reasons


def test_guard_caps_ai_stage_to_rule_constraints() -> None:
    candidate = _make_candidate(trade_stage=TradeStage.WATCH)
    review = ScreeningAiReviewResult(
        environment_ok=True,
        trade_stage=TradeStage.ADD_ON_STRENGTH,
        entry_maturity=EntryMaturity.HIGH,
        setup_type=SetupType.TREND_BREAKOUT,
        risk_level="low",
        initial_position="1/2",
        stop_loss_rule="跌破MA20离场",
        take_profit_plan="沿5日线止盈",
        invalidation_rule="放量长阴失效",
        reasoning_summary="AI 比规则更激进",
        confidence=0.9,
        result_source="rules_plus_ai",
        is_fallback=False,
        fallback_reason=None,
    )

    guarded = ScreeningAiReviewGuard().apply(candidate, review)

    assert guarded.trade_stage == TradeStage.WATCH
    assert "rule_conflict" in guarded.downgrade_reasons


def test_build_rules_fallback_review_marks_fallback_source() -> None:
    candidate = _make_candidate(
        trade_stage=TradeStage.FOCUS,
        entry_maturity=EntryMaturity.MEDIUM,
        setup_type=SetupType.TREND_BREAKOUT,
    )

    review = build_rules_fallback_review(candidate, fallback_reason="invalid_json")

    assert review.result_source == "rules_fallback"
    assert review.is_fallback is True
    assert review.fallback_reason == "invalid_json"
    assert review.trade_stage == TradeStage.FOCUS
