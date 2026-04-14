from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional

from src.schemas.trading_types import (
    CandidateDecision,
    EntryMaturity,
    RiskLevel,
    SetupType,
    TradeStage,
)


ResultSource = str


def _serialize(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, list):
        return [_serialize(item) for item in value]
    if isinstance(value, dict):
        return {key: _serialize(item) for key, item in value.items()}
    return value


@dataclass
class ScreeningAiReviewResult:
    environment_ok: bool
    trade_stage: TradeStage
    entry_maturity: EntryMaturity
    setup_type: SetupType
    risk_level: RiskLevel | str | None
    initial_position: Optional[str]
    stop_loss_rule: Optional[str]
    take_profit_plan: Optional[str]
    invalidation_rule: Optional[str]
    reasoning_summary: str
    confidence: float
    result_source: ResultSource
    is_fallback: bool
    fallback_reason: Optional[str]
    downgrade_reasons: list[str] = field(default_factory=list)
    ai_query_id: Optional[str] = None
    ai_summary: Optional[str] = None
    ai_operation_advice: Optional[str] = None
    prompt_version: Optional[str] = None
    model_name: Optional[str] = None
    parse_status: Optional[str] = None
    retry_count: int = 0
    raw_model_output: Optional[str] = None
    raw_payload: Optional[Dict[str, Any]] = None

    def to_payload(self) -> Dict[str, Any]:
        return {
            "environment_ok": _serialize(self.environment_ok),
            "trade_stage": _serialize(self.trade_stage),
            "entry_maturity": _serialize(self.entry_maturity),
            "setup_type": _serialize(self.setup_type),
            "risk_level": _serialize(self.risk_level),
            "initial_position": self.initial_position,
            "stop_loss_rule": self.stop_loss_rule,
            "take_profit_plan": self.take_profit_plan,
            "invalidation_rule": self.invalidation_rule,
            "reasoning_summary": self.reasoning_summary,
            "confidence": self.confidence,
            "result_source": self.result_source,
            "is_fallback": self.is_fallback,
            "fallback_reason": self.fallback_reason,
            "downgrade_reasons": list(self.downgrade_reasons),
            "ai_query_id": self.ai_query_id,
            "ai_summary": self.ai_summary,
            "ai_operation_advice": self.ai_operation_advice,
            "prompt_version": self.prompt_version,
            "model_name": self.model_name,
            "parse_status": self.parse_status,
            "retry_count": self.retry_count,
            "raw_model_output": self.raw_model_output,
            "raw_payload": _serialize(self.raw_payload),
        }


def build_rules_fallback_review(
    candidate: CandidateDecision,
    fallback_reason: str,
    *,
    prompt_version: Optional[str] = None,
    model_name: Optional[str] = None,
    parse_status: Optional[str] = None,
    retry_count: int = 0,
    raw_model_output: Optional[str] = None,
) -> ScreeningAiReviewResult:
    trade_plan = candidate.trade_plan
    return ScreeningAiReviewResult(
        environment_ok=bool(candidate.environment_ok),
        trade_stage=candidate.trade_stage,
        entry_maturity=candidate.entry_maturity,
        setup_type=candidate.setup_type,
        risk_level=candidate.risk_level,
        initial_position=getattr(trade_plan, "initial_position", None),
        stop_loss_rule=getattr(trade_plan, "stop_loss_rule", None),
        take_profit_plan=getattr(trade_plan, "take_profit_plan", None),
        invalidation_rule=getattr(trade_plan, "invalidation_rule", None),
        reasoning_summary="AI review fell back to rules.",
        confidence=0.0,
        result_source="rules_fallback",
        is_fallback=True,
        fallback_reason=fallback_reason,
        prompt_version=prompt_version,
        model_name=model_name,
        parse_status=parse_status,
        retry_count=retry_count,
        raw_model_output=raw_model_output,
    )


def normalize_screening_ai_review_payload(payload: Dict[str, Any]) -> ScreeningAiReviewResult:
    required_fields = (
        "environment_ok",
        "trade_stage",
        "entry_maturity",
        "setup_type",
        "risk_level",
        "reasoning_summary",
        "confidence",
    )
    for field_name in required_fields:
        if field_name not in payload:
            raise ValueError(f"missing required field: {field_name}")

    environment_ok = payload.get("environment_ok")
    if not isinstance(environment_ok, bool):
        raise ValueError("environment_ok must be bool")

    try:
        trade_stage = TradeStage(str(payload.get("trade_stage")))
        entry_maturity = EntryMaturity(str(payload.get("entry_maturity")))
        setup_type = SetupType(str(payload.get("setup_type")))
    except ValueError as exc:
        raise ValueError("invalid enum value") from exc

    risk_level_raw = payload.get("risk_level")
    try:
        risk_level: RiskLevel | str | None = RiskLevel(str(risk_level_raw))
    except ValueError:
        risk_level = str(risk_level_raw or "").strip() or None
        if risk_level is None:
            raise ValueError("risk_level is required")

    try:
        confidence = float(payload.get("confidence", 0.0))
    except (TypeError, ValueError) as exc:
        raise ValueError("confidence must be numeric") from exc

    return ScreeningAiReviewResult(
        environment_ok=environment_ok,
        trade_stage=trade_stage,
        entry_maturity=entry_maturity,
        setup_type=setup_type,
        risk_level=risk_level,
        initial_position=_normalize_optional_text(payload.get("initial_position")),
        stop_loss_rule=_normalize_optional_text(payload.get("stop_loss_rule")),
        take_profit_plan=_normalize_optional_text(payload.get("take_profit_plan")),
        invalidation_rule=_normalize_optional_text(payload.get("invalidation_rule")),
        reasoning_summary=str(payload.get("reasoning_summary") or "").strip(),
        confidence=max(0.0, min(1.0, confidence)),
        result_source="rules_plus_ai",
        is_fallback=False,
        fallback_reason=None,
        ai_summary=_normalize_optional_text(payload.get("reasoning_summary")),
        ai_operation_advice=_normalize_optional_text(payload.get("trade_stage")),
        raw_payload=dict(payload),
    )


def _normalize_optional_text(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
