import os
import tempfile
import unittest

from src.config import Config
from src.storage import DatabaseManager


class BoardRepositoryStorageContractTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._temp_dir = tempfile.TemporaryDirectory()
        self._db_path = os.path.join(self._temp_dir.name, "board_repository.db")
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

    def test_upsert_boards_and_query_board_names_by_code(self) -> None:
        saved = self.db.upsert_boards(
            [
                {"board_name": "白酒", "board_type": "industry", "market": "cn", "source": "efinance"},
                {"board_name": "消费", "board_type": "concept", "market": "cn", "source": "efinance"},
            ]
        )

        self.assertEqual(saved, 2)

        self.db.replace_instrument_board_memberships(
            instrument_code="600519",
            memberships=[
                {"board_name": "白酒", "board_type": "industry", "market": "cn", "source": "efinance"},
                {"board_name": "消费", "board_type": "concept", "market": "cn", "source": "efinance"},
            ],
        )

        board_map = self.db.batch_get_instrument_board_names(["600519", "300750"])

        self.assertEqual(board_map["600519"], ["消费", "白酒"])
        self.assertEqual(board_map["300750"], [])

    def test_replace_instrument_board_memberships_removes_stale_memberships(self) -> None:
        self.db.replace_instrument_board_memberships(
            instrument_code="600519",
            memberships=[
                {"board_name": "白酒", "board_type": "industry", "market": "cn", "source": "efinance"},
                {"board_name": "消费", "board_type": "concept", "market": "cn", "source": "efinance"},
            ],
        )

        self.db.replace_instrument_board_memberships(
            instrument_code="600519",
            memberships=[
                {"board_name": "高端白酒", "board_type": "industry", "market": "cn", "source": "efinance"},
            ],
        )

        board_map = self.db.batch_get_instrument_board_names(["600519"])
        self.assertEqual(board_map["600519"], ["高端白酒"])

    def test_upsert_boards_is_idempotent_for_same_board_identity(self) -> None:
        self.assertEqual(
            self.db.upsert_boards(
                [{"board_name": "白酒", "board_type": "industry", "market": "cn", "source": "efinance"}]
            ),
            1,
        )
        self.assertEqual(
            self.db.upsert_boards(
                [{"board_name": "白酒", "board_type": "industry", "market": "cn", "source": "efinance"}]
            ),
            1,
        )

        board_map = self.db.batch_get_instrument_board_names(["600519"])
        self.assertEqual(board_map["600519"], [])


if __name__ == "__main__":
    unittest.main()
