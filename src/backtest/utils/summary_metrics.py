# -*- coding: utf-8 -*-
"""Helpers for reading structured summary baseline metadata."""
from __future__ import annotations

import json
from typing import Any, Dict


def load_summary_metrics(summary: Any) -> Dict[str, Any]:
    """Parse summary.metrics_json defensively."""
    payload = getattr(summary, "metrics_json", None)
    if not payload:
        return {}
    try:
        parsed = json.loads(payload)
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def get_sample_baseline(summary: Any) -> Dict[str, Any]:
    """Return structured sample baseline metadata for a summary."""
    metrics = load_summary_metrics(summary)
    baseline = metrics.get("sample_baseline")
    return baseline if isinstance(baseline, dict) else {}


def get_aggregatable_sample_count(summary: Any) -> int:
    """Return the number of samples that actually contributed to metrics."""
    baseline = get_sample_baseline(summary)
    value = baseline.get("aggregatable_sample_count")
    if isinstance(value, int):
        return value
    sample_count = getattr(summary, "sample_count", None)
    return sample_count if isinstance(sample_count, int) else 0
