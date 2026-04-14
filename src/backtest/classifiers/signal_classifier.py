# -*- coding: utf-8 -*-
"""Signal classifier: trade_stage → (signal_family, evaluator_type).

Pure logic — no DB access, no side effects.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


_ENTRY_STAGES = frozenset({"probe_entry", "add_on_strength"})
_OBSERVATION_STAGES = frozenset({"watch", "focus", "stand_aside", "reject"})

_AI_CONFIDENCE_THRESHOLD = 0.6


@dataclass(frozen=True)
class ClassificationResult:
    signal_family: str      # entry / exit / observation
    evaluator_type: str     # entry / exit / observation
    effective_trade_stage: str
    ai_overridden: bool = False


class SignalClassifier:
    """Maps trade_stage to signal family and evaluator type."""

    @staticmethod
    def classify(
        trade_stage: Optional[str],
        ai_trade_stage: Optional[str] = None,
        ai_confidence: Optional[float] = None,
        has_exit_plan: bool = False,
    ) -> ClassificationResult:
        # Exit plan takes highest priority
        if has_exit_plan:
            return ClassificationResult(
                signal_family="exit",
                evaluator_type="exit",
                effective_trade_stage=trade_stage or "unknown",
            )

        # AI override if confidence meets threshold
        effective_stage = trade_stage
        ai_overridden = False
        if (
            ai_trade_stage is not None
            and ai_confidence is not None
            and ai_confidence >= _AI_CONFIDENCE_THRESHOLD
        ):
            effective_stage = ai_trade_stage
            ai_overridden = True

        # Classify based on effective stage
        if effective_stage in _ENTRY_STAGES:
            return ClassificationResult(
                signal_family="entry",
                evaluator_type="entry",
                effective_trade_stage=effective_stage,
                ai_overridden=ai_overridden,
            )

        # Default: observation (covers watch, focus, stand_aside, reject, None, unknown)
        return ClassificationResult(
            signal_family="observation",
            evaluator_type="observation",
            effective_trade_stage=effective_stage or "unknown",
            ai_overridden=ai_overridden,
        )
