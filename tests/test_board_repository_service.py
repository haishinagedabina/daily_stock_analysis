import os
import tempfile
import unittest

from src.config import Config
from src.storage import DatabaseManager


class BoardRepositoryTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._temp_dir = tempfile.TemporaryDirectory()
        self._db_path = os.path.join(self._temp_dir.name, "board_repo_service.db")
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

    def test_repository_upserts_and_reads_board_names(self) -> None:
        from src.repositories.board_repository import BoardRepository

        repo = BoardRepository(db_manager=self.db)

        saved = repo.replace_memberships(
            instrument_code="600519",
            memberships=[
                {"board_name": "白酒", "board_type": "industry", "market": "cn", "source": "efinance"},
                {"board_name": "消费", "board_type": "concept", "market": "cn", "source": "efinance"},
            ],
        )

        self.assertEqual(saved, 2)
        self.assertEqual(
            repo.batch_get_board_names_by_codes(["600519", "300750"]),
            {"600519": ["消费", "白酒"], "300750": []},
        )


if __name__ == "__main__":
    unittest.main()
