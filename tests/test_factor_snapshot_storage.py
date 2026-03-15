import os
import tempfile
import unittest
from datetime import date

from src.config import Config
from src.storage import DatabaseManager


class FactorSnapshotStorageTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._temp_dir = tempfile.TemporaryDirectory()
        self._db_path = os.path.join(self._temp_dir.name, "test_factor_snapshot.db")
        os.environ["DATABASE_PATH"] = self._db_path

        Config.reset_instance()
        DatabaseManager.reset_instance()
        self.db = DatabaseManager.get_instance()

    def tearDown(self) -> None:
        DatabaseManager.reset_instance()
        Config.reset_instance()
        os.environ.pop("DATABASE_PATH", None)
        self._temp_dir.cleanup()

    def test_replace_factor_snapshots_for_trade_date(self) -> None:
        saved = self.db.replace_factor_snapshots(
            trade_date=date(2026, 3, 13),
            snapshots=[
                {
                    "code": "600519",
                    "close": 1500.0,
                    "pct_chg": 2.5,
                    "ma5": 1492.0,
                    "ma10": 1485.0,
                    "ma20": 1470.0,
                    "ma60": 1420.0,
                    "volume_ratio": 1.6,
                    "turnover_rate": 3.2,
                    "trend_score": 85.0,
                    "liquidity_score": 90.0,
                    "risk_flags": ["none"],
                },
                {
                    "code": "000001",
                    "close": 12.1,
                    "pct_chg": 1.2,
                    "ma5": 12.0,
                    "ma10": 11.9,
                    "ma20": 11.8,
                    "ma60": 11.5,
                    "volume_ratio": 1.1,
                    "turnover_rate": 2.1,
                    "trend_score": 70.0,
                    "liquidity_score": 75.0,
                    "risk_flags": ["volume_soft"],
                },
            ],
        )

        self.assertEqual(saved, 2)
        snapshots = self.db.list_factor_snapshots(trade_date=date(2026, 3, 13))
        self.assertEqual([item["code"] for item in snapshots], ["000001", "600519"])
        self.assertEqual(snapshots[1]["risk_flags"], ["none"])

        replaced = self.db.replace_factor_snapshots(
            trade_date=date(2026, 3, 13),
            snapshots=[
                {
                    "code": "600519",
                    "close": 1510.0,
                    "pct_chg": 3.0,
                    "ma5": 1495.0,
                    "ma10": 1488.0,
                    "ma20": 1475.0,
                    "ma60": 1425.0,
                    "volume_ratio": 1.8,
                    "turnover_rate": 3.5,
                    "trend_score": 88.0,
                    "liquidity_score": 92.0,
                    "risk_flags": ["none"],
                }
            ],
        )
        self.assertEqual(replaced, 1)
        snapshots_after = self.db.list_factor_snapshots(trade_date=date(2026, 3, 13))
        self.assertEqual(len(snapshots_after), 1)
        self.assertEqual(snapshots_after[0]["close"], 1510.0)


if __name__ == "__main__":
    unittest.main()
