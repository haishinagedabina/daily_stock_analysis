# -*- coding: utf-8 -*-
"""EntrySignalEvaluator: forward returns, MAE/MFE, drawdown, signal quality."""
from __future__ import annotations

from typing import Any, List, Optional

from src.backtest.evaluators.base_evaluator import BaseEvaluator, EvaluationResult

_DEFAULT_STOP_PCT = -3.0
_DEFAULT_TP_PCT = 5.0


class EntrySignalEvaluator(BaseEvaluator):
    """Evaluates entry signals using forward price bars."""

    @staticmethod
    def evaluate(
        entry_price: float,
        forward_bars: List[Any],
        take_profit_pct: Optional[float] = None,
        stop_loss_pct: Optional[float] = None,
        **kwargs,
    ) -> EvaluationResult:
        if not forward_bars or entry_price <= 0:
            return EvaluationResult()

        closes = [bar.close for bar in forward_bars]
        lows = [bar.low for bar in forward_bars]
        highs = [bar.high for bar in forward_bars]

        # Forward returns
        def _ret(idx):
            if idx < len(closes):
                return (closes[idx] - entry_price) / entry_price * 100
            return None

        forward_return_1d = _ret(0)
        forward_return_3d = _ret(2)
        forward_return_5d = _ret(4)
        forward_return_10d = _ret(9)

        # MAE / MFE
        min_low = min(lows)
        max_high = max(highs)
        mae = (min_low - entry_price) / entry_price * 100
        mfe = (max_high - entry_price) / entry_price * 100

        # Max drawdown from peak
        peak = entry_price
        max_dd = 0.0
        for bar in forward_bars:
            if bar.high > peak:
                peak = bar.high
            dd = (bar.low - peak) / peak * 100
            if dd < max_dd:
                max_dd = dd

        # Signal quality score
        abs_mae = abs(mae)
        if mfe + abs_mae > 0:
            signal_quality_score = mfe / (mfe + abs_mae)
        else:
            signal_quality_score = 0.0

        # Plan success (take-profit vs stop-loss)
        plan_success = None
        if take_profit_pct is not None and stop_loss_pct is not None:
            tp_price = entry_price * (1 + take_profit_pct / 100)
            sl_price = entry_price * (1 + stop_loss_pct / 100)
            plan_success = False
            for bar in forward_bars:
                sl_hit = bar.low <= sl_price
                tp_hit = bar.high >= tp_price
                if tp_hit and not sl_hit:
                    plan_success = True
                    break
                if sl_hit:
                    plan_success = False
                    break
                if tp_hit and sl_hit:
                    # Ambiguous — conservative: stop first
                    plan_success = False
                    break

        return EvaluationResult(
            forward_return_1d=forward_return_1d,
            forward_return_3d=forward_return_3d,
            forward_return_5d=forward_return_5d,
            forward_return_10d=forward_return_10d,
            mae=mae,
            mfe=mfe,
            max_drawdown_from_peak=round(max_dd, 2),
            holding_days=len(forward_bars),
            plan_success=plan_success,
            signal_quality_score=round(signal_quality_score, 4),
            outcome="win" if (forward_return_5d or 0) > 0 else "loss",
        )
