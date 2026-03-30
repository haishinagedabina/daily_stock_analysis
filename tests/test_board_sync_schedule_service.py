import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from src.services.board_sync_schedule_service import BoardSyncScheduleService


class BoardSyncScheduleServiceTestCase(unittest.TestCase):
    def _build_config(self):
        return SimpleNamespace(
            trading_day_check_enabled=True,
        )

    @patch("src.services.board_sync_schedule_service.get_open_markets_today", return_value=set())
    def test_run_once_skips_when_target_market_is_closed(self, _mock_open_markets) -> None:
        board_sync_service = MagicMock()
        db = MagicMock()
        service = BoardSyncScheduleService(
            config=self._build_config(),
            board_sync_service=board_sync_service,
            db_manager=db,
        )

        result = service.run_once(force_run=False, market="cn")

        self.assertEqual(result["status"], "skipped")
        self.assertEqual(result["reason"], "non_trading_day")
        board_sync_service.sync_codes.assert_not_called()

    @patch("src.services.board_sync_schedule_service.get_open_markets_today", return_value={"cn"})
    def test_run_once_syncs_active_instruments_on_trading_day(self, _mock_open_markets) -> None:
        board_sync_service = MagicMock()
        board_sync_service.sync_codes.return_value = {
            "processed": 2,
            "synced": 2,
            "missing": 0,
            "failed": 0,
        }
        db = MagicMock()
        db.list_instruments.return_value = [
            {"code": "600519"},
            {"code": "300750"},
        ]
        service = BoardSyncScheduleService(
            config=self._build_config(),
            board_sync_service=board_sync_service,
            db_manager=db,
        )

        result = service.run_once(force_run=False, market="cn")

        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["processed"], 2)
        self.assertEqual(result["synced"], 2)
        db.list_instruments.assert_called_once_with(market="cn", listing_status="active", exclude_st=True)
        board_sync_service.sync_codes.assert_called_once_with(["600519", "300750"], market="cn", source="efinance")

    @patch("src.services.board_sync_schedule_service.get_open_markets_today", return_value={"cn"})
    def test_run_once_returns_failed_payload_when_sync_raises(self, _mock_open_markets) -> None:
        board_sync_service = MagicMock()
        board_sync_service.sync_codes.side_effect = RuntimeError("sync failed")
        db = MagicMock()
        db.list_instruments.return_value = [{"code": "600519"}]
        service = BoardSyncScheduleService(
            config=self._build_config(),
            board_sync_service=board_sync_service,
            db_manager=db,
        )

        result = service.run_once(force_run=False, market="cn")

        self.assertEqual(result["status"], "failed")
        self.assertIn("sync failed", result["error_summary"])


if __name__ == "__main__":
    unittest.main()
