import os
import sqlite3
import tempfile
import unittest

from sqlalchemy import inspect

from src.config import Config
from src.storage import DatabaseManager


class BoardStorageTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._temp_dir = tempfile.TemporaryDirectory()
        self._db_path = os.path.join(self._temp_dir.name, "legacy_board_storage.db")
        self._create_legacy_db()
        os.environ["DATABASE_PATH"] = self._db_path
        Config.reset_instance()
        DatabaseManager.reset_instance()

    def tearDown(self) -> None:
        DatabaseManager.reset_instance()
        Config.reset_instance()
        os.environ.pop("DATABASE_PATH", None)
        self._temp_dir.cleanup()

    def _create_legacy_db(self) -> None:
        conn = sqlite3.connect(self._db_path)
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE instrument_master (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code VARCHAR(16) NOT NULL UNIQUE,
                name VARCHAR(64) NOT NULL,
                market VARCHAR(16) NOT NULL DEFAULT 'cn',
                exchange VARCHAR(16),
                listing_status VARCHAR(16) NOT NULL DEFAULT 'active',
                is_st BOOLEAN NOT NULL DEFAULT 0,
                industry VARCHAR(64),
                list_date DATE,
                updated_at DATETIME
            )
            """
        )
        conn.commit()
        conn.close()

    def test_database_initialization_creates_board_tables_for_legacy_db(self) -> None:
        db = DatabaseManager.get_instance()

        table_names = set(inspect(db._engine).get_table_names())

        self.assertIn("board_master", table_names)
        self.assertIn("instrument_board_membership", table_names)


if __name__ == "__main__":
    unittest.main()
