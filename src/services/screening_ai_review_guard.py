from __future__ import annotations

from src.schemas.screening_ai_review import ScreeningAiReviewResult
from src.schemas.trading_types import CandidateDecision, EntryMaturity, SetupType, TradeStage


_STAGE_ORDER = {
    TradeStage.STAND_ASIDE: 0,
    TradeStage.REJECT: 0,
    TradeStage.WATCH: 1,
    TradeStage.FOCUS: 2,
    TradeStage.PROBE_ENTRY: 3,
    TradeStage.ADD_ON_STRENGTH: 4,
}


class ScreeningAiReviewGuard:
    def apply(self, candidate: CandidateDecision, review: ScreeningAiReviewResult) -> ScreeningAiReviewResult:
        guarded = ScreeningAiReviewResult(**review.__dict__)

        if not guarded.environment_ok and _is_higher_than(guarded.trade_stage, TradeStage.WATCH):
            guarded.trade_stage = TradeStage.WATCH
            guarded.downgrade_reasons.append("environment_constraint")

        if guarded.setup_type == SetupType.NONE and guarded.entry_maturity == EntryMaturity.HIGH:
            guarded.entry_maturity = EntryMaturity.MEDIUM
            guarded.downgrade_reasons.append("setup_constraint")

        if guarded.trade_stage in {TradeStage.PROBE_ENTRY, TradeStage.ADD_ON_STRENGTH}:
            if not guarded.stop_loss_rule:
                guarded.trade_stage = TradeStage.FOCUS
                guarded.downgrade_reasons.append("missing_stop_anchor")
            elif not guarded.take_profit_plan or not guarded.invalidation_rule:
                guarded.trade_stage = TradeStage.FOCUS
                guarded.downgrade_reasons.append("execution_plan_incomplete")

        if _is_higher_than(guarded.trade_stage, candidate.trade_stage):
            guarded.trade_stage = candidate.trade_stage
            guarded.downgrade_reasons.append("rule_conflict")

        deduped: list[str] = []
        for reason in guarded.downgrade_reasons:
            if reason not in deduped:
                deduped.append(reason)
        guarded.downgrade_reasons = deduped
        return guarded


def _is_higher_than(left: TradeStage, right: TradeStage) -> bool:
    return _STAGE_ORDER.get(left, -1) > _STAGE_ORDER.get(right, -1)
