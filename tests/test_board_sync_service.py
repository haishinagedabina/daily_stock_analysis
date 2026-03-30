import os
import tempfile
import unittest

from src.config import Config
from src.storage import DatabaseManager


class _FakeFetcherManager:
    def __init__(self, payload_by_code):
        self.payload_by_code = payload_by_code
        self.calls = []

    def get_belong_boards(self, stock_code: str):
        self.calls.append(stock_code)
        return self.payload_by_code.get(stock_code, [])


class BoardSyncServiceTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._temp_dir = tempfile.TemporaryDirectory()
        self._db_path = os.path.join(self._temp_dir.name, "board_sync.db")
        os.environ["DATABASE_PATH"] = self._db_path
        Config.reset_instance()
        DatabaseManager.reset_instance()
        self.db = DatabaseManager.get_instance()
        self.db.upsert_instruments(
            [
                {"code": "600519", "name": "贵州茅台", "market": "cn", "listing_status": "active", "is_st": False},
                {"code": "300750", "name": "宁德时代", "market": "cn", "listing_status": "active", "is_st": False},
            ]
        )

    def tearDown(self) -> None:
        DatabaseManager.reset_instance()
        Config.reset_instance()
        os.environ.pop("DATABASE_PATH", None)
        self._temp_dir.cleanup()

    def test_sync_codes_persists_board_memberships(self) -> None:
        from src.services.board_sync_service import BoardSyncService

        manager = _FakeFetcherManager(
            {
                "600519": [{"name": "白酒", "type": "industry"}, {"board_name": "消费", "type": "concept"}],
                "300750": [{"所属板块": "新能源", "type_name": "concept"}],
            }
        )
        service = BoardSyncService(db_manager=self.db, fetcher_manager=manager)

        result = service.sync_codes(["600519", "300750"])

        self.assertEqual(result["processed"], 2)
        self.assertEqual(result["synced"], 2)
        self.assertEqual(result["missing"], 0)
        self.assertEqual(result["failed"], 0)
        self.assertEqual(manager.calls, ["600519", "300750"])
        self.assertEqual(
            self.db.batch_get_instrument_board_names(["600519", "300750"]),
            {"600519": ["消费", "白酒"], "300750": ["新能源"]},
        )


if __name__ == "__main__":
    unittest.main()
