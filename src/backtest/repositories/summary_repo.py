# -*- coding: utf-8 -*-
"""Repository for FiveLayerBacktestGroupSummary CRUD operations."""
from __future__ import annotations

import logging
from typing import Any, List, Optional

from src.backtest.models.backtest_models import FiveLayerBacktestGroupSummary
from src.storage import DatabaseManager

logger = logging.getLogger(__name__)


class SummaryRepository:
    """Upsert/query for five_layer_backtest_group_summaries."""

    def __init__(self, db_manager: Optional[DatabaseManager] = None):
        self.db = db_manager or DatabaseManager.get_instance()

    def upsert_summary(
        self,
        backtest_run_id: str,
        group_type: str,
        group_key: str,
        sample_count: int = 0,
        **kwargs: Any,
    ) -> FiveLayerBacktestGroupSummary:
        with self.db.get_session() as session:
            existing = (
                session.query(FiveLayerBacktestGroupSummary)
                .filter(
                    FiveLayerBacktestGroupSummary.backtest_run_id == backtest_run_id,
                    FiveLayerBacktestGroupSummary.group_type == group_type,
                    FiveLayerBacktestGroupSummary.group_key == group_key,
                )
                .first()
            )
            if existing is not None:
                existing.sample_count = sample_count
                for k, v in kwargs.items():
                    if hasattr(existing, k):
                        setattr(existing, k, v)
                session.commit()
                session.refresh(existing)
                return existing

            summary = FiveLayerBacktestGroupSummary(
                backtest_run_id=backtest_run_id,
                group_type=group_type,
                group_key=group_key,
                sample_count=sample_count,
                **kwargs,
            )
            session.add(summary)
            session.commit()
            session.refresh(summary)
            return summary

    def get_by_run(
        self,
        backtest_run_id: str,
        group_type: Optional[str] = None,
    ) -> List[FiveLayerBacktestGroupSummary]:
        with self.db.get_session() as session:
            q = session.query(FiveLayerBacktestGroupSummary).filter(
                FiveLayerBacktestGroupSummary.backtest_run_id == backtest_run_id
            )
            if group_type is not None:
                q = q.filter(FiveLayerBacktestGroupSummary.group_type == group_type)
            return q.all()
