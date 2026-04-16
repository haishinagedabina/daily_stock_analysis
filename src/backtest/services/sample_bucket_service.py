# -*- coding: utf-8 -*-
"""Sample origin/bucket and timing label helpers for backtest evaluations."""
from __future__ import annotations

from typing import Any, Dict, Optional


_ENTRY_STAGES = frozenset({"probe_entry", "add_on_strength"})
_BOUNDARY_STAGES = frozenset({"focus", "watch"})
_NOISE_STAGES = frozenset({"stand_aside", "reject"})

_TOO_EARLY_MAE_THRESHOLD = 3.0
_TOO_LATE_MAE_THRESHOLD = 1.0
_TOO_LATE_MFE_THRESHOLD = 2.0


class SampleBucketService:
    """Pure helper methods for sample attribution and timing heuristics."""

    @staticmethod
    def resolve_sample_origin(candidate: Dict[str, Any]) -> str:
        return str(candidate.get("sample_origin") or "selected")

    @staticmethod
    def resolve_sample_bucket(
        signal_family: Optional[str],
        effective_trade_stage: Optional[str],
        entry_maturity: Optional[str],
    ) -> str:
        stage = str(effective_trade_stage or "").lower()
        maturity = str(entry_maturity or "").lower()

        if signal_family == "entry" and stage in _ENTRY_STAGES and maturity == "high":
            return "core"
        if stage in _NOISE_STAGES or maturity == "low":
            return "noise"
        if stage in _BOUNDARY_STAGES or maturity == "medium" or signal_family == "observation":
            return "boundary"
        return "noise"

    @staticmethod
    def resolve_entry_timing(
        signal_family: Optional[str],
        entry_fill_status: Optional[str],
        mae: Optional[float],
        mfe: Optional[float],
        forward_return_5d: Optional[float],
    ) -> Dict[str, Any]:
        if signal_family != "entry":
            return {
                "entry_timing_label": "not_applicable",
                "early_pullback_pct": None,
                "late_entry_gap_pct": None,
                "missed_best_entry": False,
            }

        if entry_fill_status != "filled":
            return {
                "entry_timing_label": "not_evaluable",
                "early_pullback_pct": None,
                "late_entry_gap_pct": None,
                "missed_best_entry": False,
            }

        early_pullback_pct = abs(min(float(mae or 0.0), 0.0)) if mae is not None else None
        late_entry_gap_pct = round(float(mfe or 0.0), 4) if mfe is not None else None

        if early_pullback_pct is not None and early_pullback_pct >= _TOO_EARLY_MAE_THRESHOLD:
            return {
                "entry_timing_label": "too_early",
                "early_pullback_pct": round(early_pullback_pct, 4),
                "late_entry_gap_pct": late_entry_gap_pct,
                "missed_best_entry": False,
            }

        exhausted_move = (
            early_pullback_pct is not None
            and early_pullback_pct <= _TOO_LATE_MAE_THRESHOLD
            and late_entry_gap_pct is not None
            and late_entry_gap_pct <= _TOO_LATE_MFE_THRESHOLD
            and forward_return_5d is not None
            and forward_return_5d <= 0
        )
        if exhausted_move:
            return {
                "entry_timing_label": "too_late",
                "early_pullback_pct": round(early_pullback_pct, 4),
                "late_entry_gap_pct": late_entry_gap_pct,
                "missed_best_entry": True,
            }

        return {
            "entry_timing_label": "on_time",
            "early_pullback_pct": round(early_pullback_pct, 4) if early_pullback_pct is not None else None,
            "late_entry_gap_pct": late_entry_gap_pct,
            "missed_best_entry": False,
        }
