from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from src.config import Config, get_config
from src.core.trading_calendar import get_open_markets_today
from src.services.board_sync_service import BoardSyncService
from src.storage import DatabaseManager

logger = logging.getLogger(__name__)


class BoardSyncScheduleService:
    """Scheduled board membership sync service."""

    def __init__(
        self,
        config: Optional[Config] = None,
        board_sync_service: Optional[BoardSyncService] = None,
        db_manager: Optional[DatabaseManager] = None,
    ) -> None:
        self.config = config or get_config()
        self.db = db_manager or DatabaseManager.get_instance()
        self.board_sync_service = board_sync_service or BoardSyncService(db_manager=self.db)

    def run_once(self, force_run: bool = False, market: str = "cn") -> Dict[str, Any]:
        if self._should_skip_for_trading_day(force_run=force_run, market=market):
            return {
                "status": "skipped",
                "reason": "non_trading_day",
                "market": market,
            }

        codes = self._resolve_active_codes(market=market)
        if not codes:
            return {
                "status": "skipped",
                "reason": "empty_universe",
                "market": market,
            }

        try:
            result = self.board_sync_service.sync_codes(codes, market=market, source="efinance")
            return {
                "status": "completed",
                "market": market,
                **result,
            }
        except Exception as exc:
            logger.exception("board_sync_schedule run_once failed: %s", exc)
            return {
                "status": "failed",
                "market": market,
                "error_summary": str(exc),
            }

    def _resolve_active_codes(self, market: str) -> list[str]:
        rows = self.db.list_instruments(market=market, listing_status="active", exclude_st=True)
        return [str(item.get("code", "")).strip().upper() for item in rows if str(item.get("code", "")).strip()]

    def _should_skip_for_trading_day(self, force_run: bool, market: str) -> bool:
        if force_run or not getattr(self.config, "trading_day_check_enabled", True):
            return False
        open_markets = get_open_markets_today()
        return market not in open_markets
