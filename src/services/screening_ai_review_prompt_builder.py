from __future__ import annotations

import json
from typing import Any, Dict

from src.schemas.trading_types import CandidateDecision


SCREENING_AI_REVIEW_PROMPT_VERSION = "screening_ai_review_v1"


class ScreeningAiReviewPromptBuilder:
    def build(self, candidate: CandidateDecision) -> str:
        payload = {
            "context": {
                "prompt_version": SCREENING_AI_REVIEW_PROMPT_VERSION,
                "task": "screening_second_pass_review",
            },
            "market": {
                "environment_ok": candidate.environment_ok,
                "market_regime": getattr(candidate.market_regime, "value", candidate.market_regime),
                "rule_trade_stage": getattr(candidate.trade_stage, "value", candidate.trade_stage),
                "risk_level": getattr(candidate.risk_level, "value", candidate.risk_level),
            },
            "theme": {
                "theme_tag": candidate.theme_tag,
                "theme_position": getattr(candidate.theme_position, "value", candidate.theme_position),
                "theme_score": candidate.theme_score,
                "sector_strength": candidate.sector_strength,
            },
            "stock": {
                "code": candidate.code,
                "name": candidate.name,
                "rank": candidate.rank,
                "factor_snapshot": self._compact_factor_snapshot(candidate.factor_snapshot),
            },
            "setup": {
                "setup_type": getattr(candidate.setup_type, "value", candidate.setup_type),
                "entry_maturity": getattr(candidate.entry_maturity, "value", candidate.entry_maturity),
                "setup_hit_reasons": list(candidate.setup_hit_reasons),
                "matched_strategies": list(candidate.matched_strategies),
            },
            "trade_plan": candidate.trade_plan.to_payload() if hasattr(candidate.trade_plan, "to_payload") else self._trade_plan_payload(candidate),
        }

        output_schema = {
            "environment_ok": "boolean",
            "trade_stage": "stand_aside|watch|focus|probe_entry|add_on_strength|reject",
            "entry_maturity": "low|medium|high",
            "setup_type": "bottom_divergence_breakout|low123_breakout|trend_breakout|trend_pullback|gap_breakout|limitup_structure|none",
            "risk_level": "low|medium|high",
            "initial_position": "string|null",
            "stop_loss_rule": "string|null",
            "take_profit_plan": "string|null",
            "invalidation_rule": "string|null",
            "reasoning_summary": "string",
            "confidence": "0.0~1.0",
        }

        return "\n".join(
            [
                f"prompt_version: {SCREENING_AI_REVIEW_PROMPT_VERSION}",
                "You are the screening AI second-pass review layer.",
                "Return JSON only.",
                "AI cannot override environment/theme hard constraints.",
                "If evidence is missing, missing evidence must downgrade conservatively.",
                "Do not produce any UI/report wrapper.",
                "Keep the response strictly to the review schema.",
                "Input:",
                json.dumps(payload, ensure_ascii=False, indent=2),
                "Output schema:",
                json.dumps(output_schema, ensure_ascii=False, indent=2),
            ]
        )

    @staticmethod
    def _compact_factor_snapshot(snapshot: Dict[str, Any]) -> Dict[str, Any]:
        compact: Dict[str, Any] = {}
        for key, value in (snapshot or {}).items():
            if key.lower().endswith("news") or key.lower().endswith("body"):
                continue
            compact[key] = value
        return compact

    @staticmethod
    def _trade_plan_payload(candidate: CandidateDecision) -> Dict[str, Any]:
        trade_plan = candidate.trade_plan
        if trade_plan is None:
            return {}
        return {
            "initial_position": getattr(trade_plan, "initial_position", None),
            "add_rule": getattr(trade_plan, "add_rule", None),
            "stop_loss_rule": getattr(trade_plan, "stop_loss_rule", None),
            "take_profit_plan": getattr(trade_plan, "take_profit_plan", None),
            "invalidation_rule": getattr(trade_plan, "invalidation_rule", None),
            "holding_expectation": getattr(trade_plan, "holding_expectation", None),
            "execution_note": getattr(trade_plan, "execution_note", None),
        }
