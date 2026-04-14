# -*- coding: utf-8 -*-
"""Leader stock selector service with simplified rule-based selection."""

from __future__ import annotations

from typing import Any, Dict, Iterable, Optional


class LeaderStockSelector:
    """Select a leader by limit-up first, then smallest circulation market value."""

    @staticmethod
    def _circ_mv_sort_value(snapshot: Dict[str, Any]) -> tuple[int, float, str]:
        circ_mv = snapshot.get("circ_mv")
        if circ_mv is None:
            return (1, float("inf"), str(snapshot.get("code", "")))
        return (0, float(circ_mv), str(snapshot.get("code", "")))

    def select_leader(
        self,
        theme_stocks: Iterable[str],
        stock_snapshots: Optional[Dict[str, Dict[str, Any]]] = None,
        limit_up_within_30min: Optional[str] = None,
        above_ma100: Optional[str] = None,
    ) -> tuple[Optional[str], Optional[str]]:
        """
        Select leader using simplified project rule.

        Legacy arguments are accepted for compatibility but no longer affect
        selection.
        """
        del limit_up_within_30min, above_ma100

        theme_codes = [str(code) for code in theme_stocks if str(code)]
        if not theme_codes or not stock_snapshots:
            return None, None

        limit_up_candidates = []
        for code in theme_codes:
            snapshot = dict(stock_snapshots.get(code, {}) or {})
            if snapshot.get("is_limit_up"):
                snapshot.setdefault("code", code)
                limit_up_candidates.append(snapshot)

        if not limit_up_candidates:
            return None, None

        leader_snapshot = min(limit_up_candidates, key=self._circ_mv_sort_value)
        leader_code = str(leader_snapshot.get("code") or "")
        if not leader_code:
            return None, None

        if leader_snapshot.get("circ_mv") is None:
            return leader_code, "涨停"
        return leader_code, "涨停且流通市值最小"
