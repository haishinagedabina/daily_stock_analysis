from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from src.config import Config, get_config
from src.core.trading_calendar import get_open_markets_today
from src.services.screening_notification_service import ScreeningNotificationService
from src.services.screening_task_service import ScreeningTaskService

logger = logging.getLogger(__name__)

# Statuses that indicate a successful screening run
_NOTIFY_ELIGIBLE_STATUSES = {"completed", "completed_with_ai_degraded"}


class ScreeningScheduleService:
    """全市场筛选的手动/定时触发服务。"""

    def __init__(
        self,
        config: Optional[Config] = None,
        screening_task_service: Optional[ScreeningTaskService] = None,
        notification_service: Optional[ScreeningNotificationService] = None,
    ) -> None:
        self.config = config or get_config()
        self.screening_task_service = screening_task_service or ScreeningTaskService()
        self.notification_service = notification_service or ScreeningNotificationService()

    def run_once(self, force_run: bool = False, market: str = "cn") -> Dict[str, Any]:
        if self._should_skip_for_trading_day(force_run=force_run, market=market):
            return {
                "status": "skipped",
                "reason": "non_trading_day",
                "market": market,
            }

        result = self.screening_task_service.execute_run(
            trade_date=None,
            mode=self.config.screening_default_mode,
            candidate_limit=self.config.screening_candidate_limit,
            ai_top_k=self.config.screening_ai_top_k,
            market=market,
            trigger_type="scheduled",
        )

        # Auto-notify on successful completion
        run_status = result.get("status", "")
        run_id = result.get("run_id")
        if run_id and run_status in _NOTIFY_ELIGIBLE_STATUSES:
            try:
                self.notification_service.notify_run(run_id)
            except Exception:
                logger.exception(
                    "screening_schedule notify_run failed for run_id=%s, "
                    "run result is still returned as completed",
                    run_id,
                )

        return result

    def _should_skip_for_trading_day(self, force_run: bool, market: str) -> bool:
        if force_run or not getattr(self.config, "trading_day_check_enabled", True):
            return False
        open_markets = get_open_markets_today()
        return market not in open_markets
