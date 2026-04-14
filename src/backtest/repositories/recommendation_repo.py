# -*- coding: utf-8 -*-
"""Repository for FiveLayerBacktestRecommendation CRUD operations."""
from __future__ import annotations

import logging
from typing import List, Optional

from src.backtest.models.backtest_models import FiveLayerBacktestRecommendation
from src.storage import DatabaseManager

logger = logging.getLogger(__name__)


class RecommendationRepository:
    """CRUD for five_layer_backtest_recommendations."""

    def __init__(self, db_manager: Optional[DatabaseManager] = None):
        self.db = db_manager or DatabaseManager.get_instance()

    def save_batch(
        self, recommendations: List[FiveLayerBacktestRecommendation],
    ) -> int:
        """Persist a batch of recommendations. Returns count saved."""
        if not recommendations:
            return 0
        with self.db.get_session() as session:
            session.add_all(recommendations)
            session.commit()
            for rec in recommendations:
                session.refresh(rec)
            session.expunge_all()
            return len(recommendations)

    def get_by_run(
        self,
        backtest_run_id: str,
        recommendation_level: Optional[str] = None,
    ) -> List[FiveLayerBacktestRecommendation]:
        """Get recommendations for a run, optionally filtered by level."""
        with self.db.get_session() as session:
            q = session.query(FiveLayerBacktestRecommendation).filter(
                FiveLayerBacktestRecommendation.backtest_run_id == backtest_run_id,
            )
            if recommendation_level is not None:
                q = q.filter(
                    FiveLayerBacktestRecommendation.recommendation_level
                    == recommendation_level,
                )
            return q.all()

    def get_actionable(
        self, backtest_run_id: str,
    ) -> List[FiveLayerBacktestRecommendation]:
        """Convenience: get only actionable recommendations."""
        return self.get_by_run(backtest_run_id, recommendation_level="actionable")
