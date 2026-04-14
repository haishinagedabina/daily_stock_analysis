from __future__ import annotations

from src.schemas.trading_types import CandidateDecision, EntryMaturity, SetupType, TradePlan, TradeStage
from src.services.screening_ai_review_prompt_builder import (
    SCREENING_AI_REVIEW_PROMPT_VERSION,
    ScreeningAiReviewPromptBuilder,
)


def test_prompt_builder_uses_structured_sections_and_json_only_contract() -> None:
    candidate = CandidateDecision(
        code="600519",
        name="贵州茅台",
        trade_stage=TradeStage.FOCUS,
        setup_type=SetupType.TREND_BREAKOUT,
        entry_maturity=EntryMaturity.HIGH,
        trade_plan=TradePlan(
            initial_position="1/4",
            stop_loss_rule="跌破MA20离场",
            take_profit_plan="沿5日线止盈",
            invalidation_rule="放量长阴失效",
        ),
        factor_snapshot={"close": 1500.0, "ma20": 1480.0},
    )

    prompt = ScreeningAiReviewPromptBuilder().build(candidate)

    assert f"prompt_version: {SCREENING_AI_REVIEW_PROMPT_VERSION}" in prompt
    assert '"context"' in prompt
    assert '"market"' in prompt
    assert '"theme"' in prompt
    assert '"stock"' in prompt
    assert '"setup"' in prompt
    assert '"trade_plan"' in prompt
    assert "Return JSON only" in prompt
    assert "cannot override environment/theme hard constraints" in prompt
    assert "missing evidence must downgrade conservatively" in prompt
    assert "dashboard" not in prompt.lower()
    assert "general stock commentary" not in prompt.lower()


def test_prompt_builder_includes_required_output_schema_fields() -> None:
    candidate = CandidateDecision(code="000001", name="平安银行")

    prompt = ScreeningAiReviewPromptBuilder().build(candidate)

    for field_name in (
        "environment_ok",
        "trade_stage",
        "entry_maturity",
        "setup_type",
        "risk_level",
        "initial_position",
        "stop_loss_rule",
        "take_profit_plan",
        "invalidation_rule",
        "reasoning_summary",
        "confidence",
    ):
        assert f'"{field_name}"' in prompt
