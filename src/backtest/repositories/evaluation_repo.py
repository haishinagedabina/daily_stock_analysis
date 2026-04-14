# -*- coding: utf-8 -*-
"""Repository for FiveLayerBacktestEvaluation CRUD operations."""
from __future__ import annotations

import logging
from typing import List, Optional

from src.backtest.models.backtest_models import FiveLayerBacktestEvaluation
from src.storage import DatabaseManager

logger = logging.getLogger(__name__)


class EvaluationRepository:
    """Batch save/query for five_layer_backtest_evaluations."""

    def __init__(self, db_manager: Optional[DatabaseManager] = None):
        self.db = db_manager or DatabaseManager.get_instance()

    def save_batch(self, evaluations: List[FiveLayerBacktestEvaluation]) -> int:
        """Save a batch of evaluations. Returns count saved."""
        if not evaluations:
            return 0
        with self.db.get_session() as session:
            session.add_all(evaluations)
            session.commit()
            return len(evaluations)

    def get_by_run(
        self,
        backtest_run_id: str,
        signal_family: Optional[str] = None,
    ) -> List[FiveLayerBacktestEvaluation]:
        with self.db.get_session() as session:
            q = session.query(FiveLayerBacktestEvaluation).filter(
                FiveLayerBacktestEvaluation.backtest_run_id == backtest_run_id
            )
            if signal_family is not None:
                q = q.filter(FiveLayerBacktestEvaluation.signal_family == signal_family)
            return q.all()

    def count_by_run(self, backtest_run_id: str) -> int:
        with self.db.get_session() as session:
            return (
                session.query(FiveLayerBacktestEvaluation)
                .filter(FiveLayerBacktestEvaluation.backtest_run_id == backtest_run_id)
                .count()
            )
