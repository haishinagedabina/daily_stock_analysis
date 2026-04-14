# -*- coding: utf-8 -*-
"""Sample threshold gate for controlling recommendation eligibility.

Enforces minimum sample counts before allowing display, suggestion,
or actionable recommendation generation.
"""
from __future__ import annotations

from dataclasses import dataclass


# ── Threshold constants ─────────────────────────────────────────────────────

OBSERVATION_MIN = 5       # Below: suppress from display
SUGGESTION_MIN = 20       # Below: no hypothesis/actionable
ACTIONABLE_MIN = 50       # Below: no actionable
STABILITY_MIN = 30        # Below: skip time-bucket stability calc


@dataclass(frozen=True)
class ThresholdResult:
    """Immutable result of a sample threshold check."""

    sample_count: int
    can_display: bool
    can_suggest: bool
    can_action: bool
    can_compute_stability: bool
    reason: str


class SampleThresholdGate:
    """Checks sample counts against predefined thresholds.

    Thresholds:
      - OBSERVATION_MIN (5):  minimum to show in summary
      - SUGGESTION_MIN (20):  minimum for hypothesis-level recommendation
      - ACTIONABLE_MIN (50):  minimum for actionable recommendation
      - STABILITY_MIN (30):   minimum to compute time-bucket stability
    """

    @staticmethod
    def check(sample_count: int) -> ThresholdResult:
        """Evaluate sample count against all thresholds."""
        can_display = sample_count >= OBSERVATION_MIN
        can_suggest = sample_count >= SUGGESTION_MIN
        can_action = sample_count >= ACTIONABLE_MIN
        can_stability = sample_count >= STABILITY_MIN

        if not can_display:
            reason = f"sample_count={sample_count} < OBSERVATION_MIN={OBSERVATION_MIN}: suppressed"
        elif not can_suggest:
            reason = f"sample_count={sample_count} < SUGGESTION_MIN={SUGGESTION_MIN}: display only"
        elif not can_action:
            reason = f"sample_count={sample_count} < ACTIONABLE_MIN={ACTIONABLE_MIN}: hypothesis max"
        else:
            reason = "all thresholds met"

        return ThresholdResult(
            sample_count=sample_count,
            can_display=can_display,
            can_suggest=can_suggest,
            can_action=can_action,
            can_compute_stability=can_stability,
            reason=reason,
        )
