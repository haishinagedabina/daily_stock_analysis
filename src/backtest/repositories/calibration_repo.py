# -*- coding: utf-8 -*-
"""Repository for FiveLayerBacktestCalibrationOutput CRUD operations."""
from __future__ import annotations

import logging
from typing import List, Optional

from src.backtest.models.backtest_models import FiveLayerBacktestCalibrationOutput
from src.storage import DatabaseManager

logger = logging.getLogger(__name__)


class CalibrationRepository:
    """CRUD for five_layer_backtest_calibration_outputs."""

    def __init__(self, db_manager: Optional[DatabaseManager] = None):
        self.db = db_manager or DatabaseManager.get_instance()

    def save(
        self, output: FiveLayerBacktestCalibrationOutput,
    ) -> FiveLayerBacktestCalibrationOutput:
        """Persist a single calibration output."""
        with self.db.get_session() as session:
            session.add(output)
            session.commit()
            session.refresh(output)
            return output

    def get_by_run(
        self,
        backtest_run_id: str,
    ) -> List[FiveLayerBacktestCalibrationOutput]:
        """Get all calibration outputs for a run."""
        with self.db.get_session() as session:
            return (
                session.query(FiveLayerBacktestCalibrationOutput)
                .filter(
                    FiveLayerBacktestCalibrationOutput.backtest_run_id
                    == backtest_run_id,
                )
                .all()
            )

    def get_by_name(
        self,
        backtest_run_id: str,
        calibration_name: str,
    ) -> Optional[FiveLayerBacktestCalibrationOutput]:
        """Get a specific calibration output by run and name."""
        with self.db.get_session() as session:
            return (
                session.query(FiveLayerBacktestCalibrationOutput)
                .filter(
                    FiveLayerBacktestCalibrationOutput.backtest_run_id
                    == backtest_run_id,
                    FiveLayerBacktestCalibrationOutput.calibration_name
                    == calibration_name,
                )
                .first()
            )
