# -*- coding: utf-8 -*-
"""ObservationSignalEvaluator: counterfactual — risk_avoided vs opportunity_cost."""
from __future__ import annotations

from typing import Any, List, Optional

from src.backtest.evaluators.base_evaluator import BaseEvaluator, EvaluationResult

_DEFAULT_STOP_PCT = 3.0   # typical stop-loss threshold
_DEFAULT_TP_PCT = 5.0     # typical take-profit threshold


class ObservationSignalEvaluator(BaseEvaluator):
    """Evaluates observation (non-entry) signals counterfactually."""

    @staticmethod
    def evaluate(
        hypothetical_entry_price: float,
        forward_bars: List[Any],
        stop_threshold_pct: float = _DEFAULT_STOP_PCT,
        profit_threshold_pct: float = _DEFAULT_TP_PCT,
        **kwargs,
    ) -> EvaluationResult:
        if not forward_bars or hypothetical_entry_price <= 0:
            return EvaluationResult()

        lows = [bar.low for bar in forward_bars]
        highs = [bar.high for bar in forward_bars]

        min_low = min(lows)
        max_high = max(highs)

        risk_avoided_pct = (hypothetical_entry_price - min_low) / hypothetical_entry_price * 100
        opportunity_cost_pct = (max_high - hypothetical_entry_price) / hypothetical_entry_price * 100

        stage_success = risk_avoided_pct > opportunity_cost_pct

        would_have_hit_stop = risk_avoided_pct >= stop_threshold_pct
        would_have_hit_profit = opportunity_cost_pct >= profit_threshold_pct

        return EvaluationResult(
            risk_avoided_pct=round(risk_avoided_pct, 2),
            opportunity_cost_pct=round(opportunity_cost_pct, 2),
            stage_success=stage_success,
            would_have_hit_stop=would_have_hit_stop,
            would_have_hit_profit=would_have_hit_profit,
            holding_days=len(forward_bars),
            outcome="correct_wait" if stage_success else "missed_opportunity",
        )
