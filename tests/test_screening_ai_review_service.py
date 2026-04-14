from __future__ import annotations

from unittest.mock import MagicMock

from src.schemas.trading_types import CandidateDecision, EntryMaturity, SetupType, TradeStage
from src.services.screening_ai_review_service import ScreeningAiReviewService


def _candidate() -> CandidateDecision:
    return CandidateDecision(
        code="600519",
        name="贵州茅台",
        trade_stage=TradeStage.FOCUS,
        setup_type=SetupType.TREND_BREAKOUT,
        entry_maturity=EntryMaturity.HIGH,
    )


def _valid_json(trade_stage: str = "focus") -> str:
    return (
        "{"
        f'"environment_ok": true,'
        f'"trade_stage": "{trade_stage}",'
        '"entry_maturity": "high",'
        '"setup_type": "trend_breakout",'
        '"risk_level": "medium",'
        '"initial_position": "1/4",'
        '"stop_loss_rule": "跌破MA20离场",'
        '"take_profit_plan": "沿5日线止盈",'
        '"invalidation_rule": "放量长阴失效",'
        '"reasoning_summary": "结构完整",'
        '"confidence": 0.76'
        "}"
    )


def test_service_accepts_valid_json_on_first_try() -> None:
    llm_client = MagicMock()
    llm_client.generate_text.return_value = _valid_json()

    review = ScreeningAiReviewService(llm_client=llm_client).review_candidate(_candidate())

    assert review.result_source == "rules_plus_ai"
    assert review.fallback_reason is None
    assert review.retry_count == 0
    assert review.trade_stage == TradeStage.FOCUS


def test_service_retries_once_after_invalid_json_then_accepts_valid_json() -> None:
    llm_client = MagicMock()
    llm_client.generate_text.side_effect = ["not-json", _valid_json("probe_entry")]

    review = ScreeningAiReviewService(llm_client=llm_client).review_candidate(_candidate())

    assert llm_client.generate_text.call_count == 2
    assert review.result_source == "rules_plus_ai"
    assert review.retry_count == 1
    assert review.trade_stage == TradeStage.FOCUS


def test_service_falls_back_after_two_invalid_json_responses() -> None:
    llm_client = MagicMock()
    llm_client.generate_text.side_effect = ["nope", "still-nope"]

    review = ScreeningAiReviewService(llm_client=llm_client).review_candidate(_candidate())

    assert llm_client.generate_text.call_count == 2
    assert review.result_source == "rules_fallback"
    assert review.fallback_reason == "invalid_json"


def test_service_falls_back_on_timeout_or_model_exception() -> None:
    llm_client = MagicMock()
    llm_client.generate_text.side_effect = TimeoutError("llm timeout")

    review = ScreeningAiReviewService(llm_client=llm_client).review_candidate(_candidate())

    assert review.result_source == "rules_fallback"
    assert review.fallback_reason == "timeout"


def test_service_falls_back_when_structured_output_cannot_be_normalized() -> None:
    llm_client = MagicMock()
    llm_client.generate_text.return_value = (
        "{"
        '"environment_ok": true,'
        '"trade_stage": "rocket",'
        '"entry_maturity": "high",'
        '"setup_type": "trend_breakout",'
        '"risk_level": "medium",'
        '"initial_position": "1/4",'
        '"stop_loss_rule": "跌破MA20离场",'
        '"take_profit_plan": "沿5日线止盈",'
        '"invalidation_rule": "放量长阴失效",'
        '"reasoning_summary": "bad enum",'
        '"confidence": 0.76'
        "}"
    )

    review = ScreeningAiReviewService(llm_client=llm_client).review_candidate(_candidate())

    assert review.result_source == "rules_fallback"
    assert review.fallback_reason == "normalize_failed"
