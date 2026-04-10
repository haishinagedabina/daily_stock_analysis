from __future__ import annotations

from typing import Any, Dict, Iterable, List

from src.schemas.trading_types import AiReviewDecision, CandidateDecision, TradeStage


class CandidateDecisionBuilder:
    """统一构造和补全 CandidateDecision。"""

    @staticmethod
    def build_initial(records: Iterable[Any]) -> List[CandidateDecision]:
        return [CandidateDecision.from_record(record) for record in records]

    @staticmethod
    def attach_ai_reviews(
        decisions: Iterable[CandidateDecision],
        ai_results: Dict[str, Dict[str, Any]],
        ai_top_k: int,
    ) -> List[CandidateDecision]:
        updated: List[CandidateDecision] = []
        for decision in decisions:
            ai_payload = ai_results.get(decision.code, {})
            decision.selected_for_ai = decision.rank <= ai_top_k
            review = CandidateDecisionBuilder._build_ai_review(ai_payload)
            decision.ai_review = review
            decision.has_ai_analysis = bool(
                review
                and (
                    review.ai_summary
                    or review.ai_operation_advice
                    or review.ai_reasoning
                )
            )
            updated.append(decision)
        return updated

    @staticmethod
    def _build_ai_review(ai_payload: Dict[str, Any]) -> AiReviewDecision | None:
        if not ai_payload:
            return None
        ai_trade_stage = ai_payload.get("ai_trade_stage")
        try:
            parsed_stage = TradeStage(ai_trade_stage) if ai_trade_stage else None
        except ValueError:
            parsed_stage = None
        return AiReviewDecision(
            ai_query_id=ai_payload.get("ai_query_id"),
            ai_summary=ai_payload.get("ai_summary"),
            ai_operation_advice=ai_payload.get("ai_operation_advice"),
            ai_trade_stage=parsed_stage,
            ai_reasoning=ai_payload.get("ai_reasoning", "") or "",
            ai_confidence=float(ai_payload.get("ai_confidence", 0.0) or 0.0),
            ai_environment_ok=ai_payload.get("ai_environment_ok"),
            ai_theme_alignment=ai_payload.get("ai_theme_alignment"),
            ai_entry_quality=ai_payload.get("ai_entry_quality"),
            stage_conflict=bool(ai_payload.get("stage_conflict", False)),
        )
