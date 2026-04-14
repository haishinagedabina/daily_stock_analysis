# -*- coding: utf-8 -*-
"""CandidateSelector: reads ScreeningCandidate records and extracts
five-layer snapshot fields for backtest evaluation.
"""
from __future__ import annotations

import json
import logging
from datetime import date
from typing import Any, Dict, List, Optional

from src.storage import DatabaseManager, ScreeningCandidate, ScreeningRun

logger = logging.getLogger(__name__)


class CandidateSelector:
    """Reads screening candidates and returns dicts with five-layer fields."""

    def __init__(self, db_manager: Optional[DatabaseManager] = None):
        self.db = db_manager or DatabaseManager.get_instance()

    def select_candidates(self, screening_run_id: str) -> List[Dict[str, Any]]:
        """Select all candidates from a specific screening run."""
        with self.db.get_session() as session:
            run = (
                session.query(ScreeningRun)
                .filter(ScreeningRun.run_id == screening_run_id)
                .first()
            )
            if run is None:
                return []

            candidates = (
                session.query(ScreeningCandidate)
                .filter(ScreeningCandidate.run_id == screening_run_id)
                .order_by(ScreeningCandidate.rank)
                .all()
            )
            return [
                self._to_candidate_dict(c, run.trade_date)
                for c in candidates
            ]

    def select_candidates_by_date_range(
        self,
        date_from: date,
        date_to: date,
        market: str = "cn",
    ) -> List[Dict[str, Any]]:
        """Select candidates across all completed runs within a date range."""
        with self.db.get_session() as session:
            runs = (
                session.query(ScreeningRun)
                .filter(
                    ScreeningRun.trade_date >= date_from,
                    ScreeningRun.trade_date <= date_to,
                    ScreeningRun.market == market,
                    ScreeningRun.status.in_(["completed", "completed_with_ai_degraded"]),
                )
                .all()
            )
            results = []
            for run in runs:
                candidates = (
                    session.query(ScreeningCandidate)
                    .filter(ScreeningCandidate.run_id == run.run_id)
                    .order_by(ScreeningCandidate.rank)
                    .all()
                )
                results.extend(
                    self._to_candidate_dict(c, run.trade_date)
                    for c in candidates
                )
            return results

    @staticmethod
    def _to_candidate_dict(
        candidate: ScreeningCandidate,
        trade_date: date,
    ) -> Dict[str, Any]:
        trade_plan = None
        if candidate.trade_plan_json:
            try:
                trade_plan = json.loads(candidate.trade_plan_json)
            except (json.JSONDecodeError, TypeError):
                pass

        return {
            "screening_run_id": candidate.run_id,
            "screening_candidate_id": candidate.id,
            "trade_date": trade_date,
            "code": candidate.code,
            "name": candidate.name,
            "rank": candidate.rank,
            "rule_score": candidate.rule_score,
            # Five-layer snapshot fields
            "trade_stage": candidate.trade_stage,
            "setup_type": candidate.setup_type,
            "entry_maturity": candidate.entry_maturity,
            "market_regime": candidate.market_regime,
            "theme_position": candidate.theme_position,
            "candidate_pool_level": candidate.candidate_pool_level,
            "risk_level": candidate.risk_level,
            "trade_plan": trade_plan,
            # AI override fields
            "ai_trade_stage": candidate.ai_trade_stage,
            "ai_confidence": candidate.ai_confidence,
        }
